import asyncio
import hashlib
import os
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from sqlalchemy import select

from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.models.note import Note
from app.services.embedding_config_service import EmbeddingConfigData, get_embedding_config_service
from app.utils.config import chroma_config
from app.utils.image_extractor import delete_image_directory, delete_user_all_images
from app.utils.path_tool import get_abstract_path

from .document_handler import DocumentProcessor
from .md5_manager import MD5Store
from .retrievers.hybrid_retriever import HybridRetriever


def _clear_chroma_cache():
    """
    清除 ChromaDB SharedSystemClient 内部单例缓存，避免 KeyError。
    ChromaDB 在 0.5.x+ 引入了 SharedSystemClient，它内部维护了一个全局 _instance 字典。
    当同一个进程反复创建/删除 Chroma 实例时，会抛出 KeyError（因为缓存中的 client 已被销毁）。
    在初始化前主动清除缓存，可以避免此问题。
    """
    try:
        from chromadb.api.shared_system_client import SharedSystemClient
        SharedSystemClient.clear_system_cache()
    except Exception:
        pass


@dataclass(frozen=True, slots=True)
class ChromaProjectionHealth:
    status: str
    persist_directory: str | None
    checked_at: str | None
    error_type: str | None = None
    error_message: str | None = None


class ChromaProjectionUnavailable(RuntimeError):
    """Raised when the rebuildable Chroma projection is quarantined."""


CHROMA_PROJECTION_UNAVAILABLE_MESSAGE = (
    "Chroma projection is unavailable; retry after recovery"
)


class _LazyEmbedding(Embeddings):
    """延迟加载的嵌入模型包装器

    VectorStoreService 是单例，在后台初始化完成前就可能被创建。
    直接用 init_manager.embed_model 传入 Chroma 会得到 None，
    等 Chroma 真正调 embed_documents 时就会崩溃。
    这个包装器把模型解析推迟到 embed 调用时，确保模型已就绪。
    """

    def _get_model(self):
        from app.core.background_init import init_manager
        model = init_manager.embed_model
        if model is None:
            raise RuntimeError("嵌入模型尚未初始化完成，请稍后重试")
        return model

    def embed_documents(self, texts):
        return self._get_model().embed_documents(texts)

    def embed_query(self, text):
        return self._get_model().embed_query(text)


class VectorStoreService:
    """
    向量数据库服务（单例，线程安全初始化，自动恢复 ChromaDB 缓存冲突）。

    使用双重检查锁定（Double-Checked Locking）实现线程安全的单例模式。
    之所以需要单例，是因为 ChromaDB 客户端维护了内部的连接池和缓存，
    多个实例会导致资源冲突和不可预期的 KeyError。
    """
    _instance = None
    _initialized = False
    _restart_required = False
    _init_lock = threading.Lock()
    _projection_health = ChromaProjectionHealth(
        status="not_initialized",
        persist_directory=None,
        checked_at=None,
    )

    def __new__(cls):
        # 第一重检查（无锁，性能优先）
        if cls._instance is None:
            with cls._init_lock:
                # 第二重检查（加锁后，确保线程安全）
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if VectorStoreService._restart_required:
            raise ChromaProjectionUnavailable(
                "projection rebuild completed; restart the process before opening Chroma"
            )
        if VectorStoreService._initialized:
            return

        with VectorStoreService._init_lock:
            if VectorStoreService._initialized:
                return

            persist_dir = get_abstract_path(chroma_config['persist_directory'])
            # 在创建 Chroma 实例前清除缓存，避免残留的单例 client 导致 KeyError
            _clear_chroma_cache()

            try:
                self._init_chroma(persist_dir)
            except Exception as e:
                # Chroma is a rebuildable projection, but an arbitrary init
                # error never authorizes deleting its persisted source bytes.
                # Keep the directory untouched and fail closed until an
                # operator runs the explicit, manifest-backed rebuild flow.
                self._mark_projection_unhealthy(persist_dir, e)
                logger.error(
                    "Chroma projection initialization failed; persistent data was preserved and the projection was quarantined: %s",
                    e,
                    exc_info=True,
                )
                raise ChromaProjectionUnavailable(
                    "Chroma projection is unavailable; persistent data was preserved"
                ) from e

            VectorStoreService._initialized = True

    def _init_chroma(self, persist_dir: str):
        self.persist_dir = persist_dir
        create_collections = self._preflight_existing_projection(persist_dir)
        self.vectors_store = Chroma(
            collection_name=chroma_config['collection_name'],
            embedding_function=self._get_embed_model(),
            persist_directory=persist_dir,
            create_collection_if_not_exists=create_collections,
        )
        self._notes_store = Chroma(
            collection_name="notes_collection",
            embedding_function=self._get_embed_model(),
            persist_directory=persist_dir,
            create_collection_if_not_exists=create_collections,
        )
        self._user_rag_stores: dict[str, Chroma] = {}
        self._user_note_stores: dict[str, Chroma] = {}
        self.md5_store = MD5Store()
        self.hybrid_retriever = HybridRetriever(self.vectors_store)
        self.document_processor = DocumentProcessor(self.vectors_store, self.md5_store, self._get_embed_model())
        VectorStoreService._projection_health = ChromaProjectionHealth(
            status="ready",
            persist_directory=str(Path(persist_dir).resolve()),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _preflight_existing_projection(persist_dir: str) -> bool:
        """Validate an existing projection without allowing Chroma to mutate it.

        Chroma's default client applies migrations and creates missing collections
        during construction. A damaged or partial projection must instead fail
        closed before the client gets a write-capable handle. The return value is
        true only for a new/empty directory where initial collection creation is
        intentional.
        """

        persist_path = Path(persist_dir).expanduser().resolve(strict=False)
        if not persist_path.exists():
            return True
        if not persist_path.is_dir():
            raise RuntimeError(f"Chroma persist path is not a directory: {persist_path}")

        database_path = persist_path / "chroma.sqlite3"
        if not database_path.exists():
            if any(persist_path.iterdir()):
                raise RuntimeError(
                    "Chroma projection directory is non-empty but chroma.sqlite3 is missing"
                )
            return True
        if not database_path.is_file():
            raise RuntimeError(f"Chroma database is not a regular file: {database_path}")

        try:
            uri = f"{database_path.resolve(strict=True).as_uri()}?mode=ro&immutable=1"
            connection = sqlite3.connect(uri, uri=True)
            try:
                table_names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                required_tables = {"collections", "migrations"}
                missing_tables = sorted(required_tables - table_names)
                if missing_tables:
                    raise RuntimeError(
                        f"Chroma projection is missing required tables: {missing_tables}"
                    )
                collection_names = {
                    row[0] for row in connection.execute("SELECT name FROM collections")
                }
                migration_rows = connection.execute(
                    "SELECT dir, version, filename, hash FROM migrations ORDER BY dir, version"
                ).fetchall()
            finally:
                connection.close()
        except (OSError, sqlite3.Error) as exc:
            raise RuntimeError(f"Chroma projection read-only preflight failed: {exc}") from exc

        expected_collections = {chroma_config["collection_name"], "notes_collection"}
        missing_collections = sorted(expected_collections - collection_names)
        if missing_collections:
            raise RuntimeError(
                f"Chroma projection is missing required collections: {missing_collections}"
            )

        try:
            from importlib.resources import files

            from chromadb.db.migrations import find_migrations, verify_migration_sequence

            migration_root = files("chromadb.migrations")
            source_dirs = {
                child.name: child for child in migration_root.iterdir() if child.is_dir()
            }
            database_dirs = {row[0] for row in migration_rows}
            unknown_dirs = sorted(database_dirs - source_dirs.keys())
            if unknown_dirs:
                raise RuntimeError(
                    f"Chroma projection has unknown migration directories: {unknown_dirs}"
                )

            for directory_name, directory in source_dirs.items():
                database_migrations = [
                    {
                        "dir": row[0],
                        "version": row[1],
                        "filename": row[2],
                        "hash": row[3],
                        "scope": "sqlite",
                        "sql": "",
                    }
                    for row in migration_rows
                    if row[0] == directory_name
                ]
                source_migrations = find_migrations(directory, "sqlite", "md5")
                unapplied = verify_migration_sequence(
                    database_migrations,
                    source_migrations,
                )
                if unapplied:
                    raise RuntimeError(
                        "Chroma projection requires unapplied migrations; "
                        "an explicit offline rebuild or upgrade is required"
                    )
        except Exception as exc:
            raise RuntimeError(
                f"Chroma projection migration compatibility preflight failed: {exc}"
            ) from exc

        return False

    @classmethod
    def _mark_projection_unhealthy(cls, persist_dir: str, error: Exception) -> None:
        cls._initialized = False
        cls._projection_health = ChromaProjectionHealth(
            status="quarantined",
            persist_directory=str(Path(persist_dir).resolve()),
            checked_at=datetime.now(timezone.utc).isoformat(),
            error_type=type(error).__name__,
            error_message=str(error)[:500],
        )

    @classmethod
    def projection_health(cls) -> dict[str, str | None]:
        """Return a JSON-safe readiness snapshot without touching Chroma."""

        return asdict(cls._projection_health)

    @classmethod
    def rebuild_projection_from_backup(
        cls,
        bundle: str | os.PathLike[str],
        target: str | os.PathLike[str],
        *,
        quarantine_root: str | os.PathLike[str] | None = None,
    ) -> dict[str, object]:
        """Rebuild a projection from a verified offline bundle.

        The backup helper validates the manifest and every file digest, builds
        a sibling staging generation, then atomically swaps the directory. A
        running Chroma client is never retargeted in place: callers must
        restart/reinitialize the process after a successful swap.
        """

        target_path = Path(target).expanduser().resolve(strict=False)
        configured_path = Path(
            get_abstract_path(chroma_config["persist_directory"])
        ).expanduser().resolve(strict=False)
        if target_path != configured_path:
            raise ChromaProjectionUnavailable(
                "projection rebuild target must match the configured persist directory: "
                f"{configured_path}"
            )

        current = cls._instance
        if cls._initialized and current is not None:
            current_path = Path(getattr(current, "persist_dir", "")).resolve(strict=False)
            if current_path == target_path:
                raise ChromaProjectionUnavailable(
                    "projection rebuild requires a process restart; active Chroma client was not retargeted"
                )

        # Keep manifest/digest and atomic swap semantics in the offline backup
        # tool. This entry point intentionally does not open Chroma or a DB.
        from scripts.backup_restore import rebuild_projection

        result = rebuild_projection(
            bundle=Path(bundle),
            target=target_path,
            quarantine_root=Path(quarantine_root).expanduser().resolve(strict=False)
            if quarantine_root is not None
            else None,
        )
        cls._projection_health = ChromaProjectionHealth(
            status="rebuild_pending_restart",
            persist_directory=str(target_path),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
        cls._restart_required = True
        return result

    @staticmethod
    def _get_embed_model():
        """获取嵌入模型（延迟加载包装器，模型在首次调用时解析）"""
        return _LazyEmbedding()

    @staticmethod
    def _collection_suffix(user_id: str) -> str:
        return hashlib.sha1(user_id.encode("utf-8")).hexdigest()[:16]

    def _user_collection_name(self, prefix: str, user_id: str) -> str:
        return f"{prefix}_{self._collection_suffix(user_id)}"

    async def _get_user_embedding_config(self, user_id: str, db=None) -> EmbeddingConfigData:
        svc = get_embedding_config_service()
        if db is not None:
            return await svc.get_user_config(db, user_id)
        async with AsyncSessionLocal() as session:
            return await svc.get_user_config(session, user_id)

    def _create_store(self, collection_name: str, embedding_config: EmbeddingConfigData) -> Chroma:
        embed_model = get_embedding_config_service().create_embedding_model(embedding_config)
        return Chroma(
            collection_name=collection_name,
            embedding_function=embed_model,
            persist_directory=self.persist_dir,
        )

    def _reset_store(self, store: Chroma):
        try:
            store.reset_collection()
        except Exception as exc:
            logger.error("重置 Chroma collection 失败；索引重建已停止: %s", exc, exc_info=True)
            raise

    async def get_user_rag_store(self, user_id: str, db=None, reset: bool = False) -> Chroma:
        if not user_id:
            return self.vectors_store

        embedding_config = await self._get_user_embedding_config(user_id, db)
        collection_name = self._user_collection_name("rag", user_id)
        key = f"{collection_name}:{embedding_config.model_type}:{embedding_config.model_name}:{embedding_config.base_url}"
        store = self._user_rag_stores.get(key)
        if store is None:
            store = self._create_store(collection_name, embedding_config)
            self._user_rag_stores = {k: v for k, v in self._user_rag_stores.items() if not k.startswith(f"{collection_name}:")}
            self._user_rag_stores[key] = store
        if reset:
            self._reset_store(store)
        return store

    async def get_user_notes_store(self, user_id: str, db=None, reset: bool = False) -> Chroma:
        if not user_id:
            return self._notes_store

        embedding_config = await self._get_user_embedding_config(user_id, db)
        collection_name = self._user_collection_name("notes", user_id)
        key = f"{collection_name}:{embedding_config.model_type}:{embedding_config.model_name}:{embedding_config.base_url}"
        store = self._user_note_stores.get(key)
        if store is None:
            store = self._create_store(collection_name, embedding_config)
            self._user_note_stores = {k: v for k, v in self._user_note_stores.items() if not k.startswith(f"{collection_name}:")}
            self._user_note_stores[key] = store
        if reset:
            self._reset_store(store)
        return store

    async def reset_user_indexes(self, user_id: str, db=None):
        await self.get_user_rag_store(user_id, db=db, reset=True)
        await self.get_user_notes_store(user_id, db=db, reset=True)

    async def add_user_documents(self, user_id: str, documents: list[Document], db=None, ids: list[str] | None = None):
        store = await self.get_user_rag_store(user_id, db=db)
        return await asyncio.to_thread(store.add_documents, documents, ids=ids)

    async def delete_user_source_documents(self, user_id: str, source_document_id: str, db=None):
        store = await self.get_user_rag_store(user_id, db=db)
        await asyncio.to_thread(
            store.delete,
            where={"source_document_id": source_document_id},
        )

    async def rebuild_user_notes_index(self, db, user_id: str) -> int:
        store = await self.get_user_notes_store(user_id, db=db, reset=True)
        result = await db.execute(select(Note).where(Note.user_id == user_id))
        notes = result.scalars().all()
        if not notes:
            return 0

        docs = [
            Document(
                page_content=note.content,
                metadata={
                    "user_id": user_id,
                    "note_id": note.id,
                    "doc_type": "note",
                    "title": note.title,
                },
            )
            for note in notes
        ]
        ids = [note.id for note in notes]
        await asyncio.to_thread(store.add_documents, docs, ids=ids)
        return len(docs)

    async def get_bm25_retriever(self, user_id: str = None, k: int | None = None):
        if not user_id:
            return await self.hybrid_retriever.get_bm25_retriever(user_id, k)
        store = await self.get_user_rag_store(user_id)
        return await HybridRetriever(store).get_bm25_retriever(user_id, k)

    async def _get_all_documents(self) -> list[Document]:
        return await self.hybrid_retriever._get_all_documents()

    async def get_retriever(self, query: str = None, user_id: str = None, k: int | None = None):
        if not user_id:
            return await self.hybrid_retriever.get_retriever(query, user_id, k)
        store = await self.get_user_rag_store(user_id)
        return await HybridRetriever(store).get_retriever(query, user_id, k)

    @staticmethod
    async def get_dynamic_weights(query: str = None):
        return await HybridRetriever.get_dynamic_weights(query)

    async def check_md5_hex(self, md5_for_check: str, user_id: str = None) -> bool:
        return await self.md5_store.check_md5_hex(md5_for_check, user_id)

    async def save_md5_hex(self, md5_hex: str, filename: str = None, original_filename: str = None, user_id: str = None):
        await self.md5_store.save_md5_hex(md5_hex, filename, original_filename, user_id)

    def save_md5_hex_sync(self, md5_hex: str, filename: str = None, original_filename: str = None, user_id: str = None):
        self.md5_store.save_md5_hex_sync(md5_hex, filename, original_filename, user_id)

    async def delete_user_documents(self, user_id: str):
        """
        删除指定用户的所有文档（包括MD5记录）
        :param user_id: 用户ID
        """
        try:
            await self.delete_user_md5(user_id, delete_documents=True)
        except Exception as e:
            logger.error(f"【向量数据库】删除用户 {user_id} 的文档时出错: {e}")
            raise

    async def delete_user_md5(self, user_id: str, delete_documents: bool = True):
        """
        删除指定用户的MD5记录
        :param user_id: 用户ID
        :param delete_documents: 是否同时删除向量数据库中的文档（默认True）
        """
        try:
            if delete_documents:
                store = await self.get_user_rag_store(user_id)
                await asyncio.to_thread(
                    store.delete,
                    where={"user_id": user_id}
                )
                logger.info(f"【向量数据库】已删除用户 {user_id} 的所有文档")

            await self.md5_store.delete_user_md5(user_id)
            # 同步清理该用户在磁盘上存储的所有 PDF 提取图片
            # 删除文档时必须连带删除对应的图片资源，否则会留下无法被引用的"脏"文件
            delete_user_all_images(user_id)
        except Exception as e:
            logger.error(f"【向量数据库】删除用户 {user_id} 的MD5记录时出错: {e}")

    async def delete_by_filename(self, user_id: str, filename: str, delete_documents: bool = True):
        """
        通过文件名删除MD5记录及其对应的知识库内容
        :param user_id: 用户ID
        :param filename: 要删除的文件名
        :param delete_documents: 是否同时删除向量数据库中的对应文档（默认True）
        :return: 是否成功删除
        """
        try:
            md5_to_delete = await self.md5_store.delete_by_filename(user_id, filename)
            if md5_to_delete is None:
                logger.warning(f"【向量数据库】文件 {filename} 不存在于用户 {user_id} 的MD5记录中")
                return False

            logger.info(f"【向量数据库】已删除用户 {user_id} 的文件 {filename} 的MD5记录")

            if delete_documents:
                where_clause = {"$and": [{"user_id": user_id}, {"md5": md5_to_delete}]}
                store = await self.get_user_rag_store(user_id)
                await asyncio.to_thread(
                    store.delete,
                    where=where_clause
                )
                logger.info(f"【向量数据库】已删除用户 {user_id} 中文件 {filename} 对应的文档")

            # 删除该文档对应的 PDF 提取图片目录
            delete_image_directory(user_id, md5_to_delete)

            return True

        except Exception as e:
            logger.error(f"【向量数据库】删除用户 {user_id} 的文件 {filename} 时出错: {e}")
            return False

    async def delete_single_md5(self, user_id: str, md5_to_delete: str, delete_documents: bool = True):
        """
        删除单个MD5记录及其对应的知识库内容
        :param user_id: 用户ID
        :param md5_to_delete: 要删除的MD5值
        :param delete_documents: 是否同时删除向量数据库中的对应文档（默认True）
        :return: 是否成功删除
        """
        try:
            success = await self.md5_store.delete_single_md5(user_id, md5_to_delete)
            if not success:
                logger.warning(f"【向量数据库】MD5记录 {md5_to_delete} 不存在")
                return False

            logger.info(f"【向量数据库】已删除用户 {user_id} 的MD5记录: {md5_to_delete}")

            if delete_documents:
                where_clause = {"$and": [{"user_id": user_id}, {"md5": md5_to_delete}]}
                store = await self.get_user_rag_store(user_id)
                await asyncio.to_thread(
                    store.delete,
                    where=where_clause
                )
                logger.info(f"【向量数据库】已删除用户 {user_id} 中MD5为 {md5_to_delete} 的文档")

            # 清理磁盘上该用户的 PDF 提取图片
            delete_image_directory(user_id, md5_to_delete)

            return True

        except Exception as e:
            logger.error(f"【向量数据库】删除用户 {user_id} 的MD5记录 {md5_to_delete} 时出错: {e}")
            return False

    async def get_md5_info(self, user_id: str, md5_value: str):
        """
        获取MD5对应的文档信息
        :param user_id: 用户ID
        :param md5_value: MD5值
        :return: MD5信息字典，不存在返回None
        """
        try:
            return await self.md5_store.get_md5_info(user_id, md5_value)
        except Exception as e:
            logger.error(f"【向量数据库】获取MD5信息 {md5_value} 时出错: {e}")
            return None

    async def get_all_md5_records(self, user_id: str):
        """
        获取用户的所有MD5记录
        :param user_id: 用户ID
        :return: MD5记录列表
        """
        try:
            records = await self.md5_store.get_all_md5_records(user_id)
            logger.info(f"【向量数据库】获取用户 {user_id} 的MD5记录，共 {len(records)} 条")
            return records
        except Exception as e:
            logger.error(f"【向量数据库】获取用户 {user_id} 的MD5记录时出错: {e}")
            return []

    async def get_user_documents(self, user_id: str = None):
        """
        获取用户的知识库文档列表
        :param user_id: 用户ID，如果为None则获取所有文档
        :return: 文档信息列表，包含文件名、文档数量、预览等信息
        """
        try:
            where_clause = {"user_id": user_id} if user_id else None
            store = await self.get_user_rag_store(user_id) if user_id else self.vectors_store
            all_docs = await asyncio.to_thread(
                store.get,
                include=['documents', 'metadatas'],
                where=where_clause
            )

            docs_info = {}

            for i, doc_id in enumerate(all_docs['ids']):
                metadata = all_docs['metadatas'][i] if i < len(all_docs['metadatas']) else {}
                content = all_docs['documents'][i] if i < len(all_docs['documents']) else ""

                # 优先使用 metadata 中保存的 original_filename（用户上传时的原始文件名）
                # 因为 source 可能存的是临时文件的完整路径（如 C:\Users\...\tmp123.pdf），
                # 而 original_filename 才是用户看到的文件名
                source = metadata.get('source', metadata.get('filename', 'unknown'))
                if isinstance(source, str) and '\\' in source:
                    source = os.path.basename(source)
                filename = metadata.get('original_filename', source)

                original_filename = metadata.get('original_filename', filename)
                if filename not in docs_info:
                    docs_info[filename] = {
                        'id': doc_id,
                        'filename': filename,
                        'original_filename': original_filename,
                        'user_id': metadata.get('user_id'),
                        'chunk_count': 0,
                        'preview': "",
                        'created_at': metadata.get('created_at')
                    }

                docs_info[filename]['chunk_count'] += 1

                if not docs_info[filename]['preview'] and content:
                    preview_length = 100
                    docs_info[filename]['preview'] = content[:preview_length] + ("..." if len(content) > preview_length else "")

            result = list(docs_info.values())
            logger.info(f"【向量数据库】获取用户 {user_id} 的知识库文档，共 {len(result)} 个文件")
            return result

        except Exception as e:
            logger.error(f"【向量数据库】获取用户 {user_id} 的知识库文档时出错: {e}")
            raise

    async def get_document_detail(self, user_id: str, filename: str):
        """
        获取文档的详细内容
        :param user_id: 用户ID
        :param filename: 文件名
        :return: 文档详情信息，包含完整内容、图片列表和每段文本与图片的对应关系
        """
        try:
            where_clause = {"user_id": user_id}
            store = await self.get_user_rag_store(user_id)
            all_docs = await asyncio.to_thread(
                store.get,
                include=['documents', 'metadatas'],
                where=where_clause
            )

            doc_info = None
            full_content = []
            chunk_count = 0
            all_images = set()
            doc_md5 = None
            chunks = []

            for i, doc_id in enumerate(all_docs['ids']):
                metadata = all_docs['metadatas'][i] if i < len(all_docs['metadatas']) else {}
                content = all_docs['documents'][i] if i < len(all_docs['documents']) else ""

                source = metadata.get('source', metadata.get('filename', ''))
                if isinstance(source, str):
                    source_name = os.path.basename(source)
                else:
                    source_name = str(source)
                original_filename = metadata.get('original_filename', '')

                # 同时匹配 source 和 original_filename，兼容不同切片方式写入的 metadata
                if source_name == filename or original_filename == filename:
                    if not doc_info:
                        doc_info = {
                            'id': doc_id,
                            'filename': filename,
                            'user_id': metadata.get('user_id'),
                            'chunk_count': 0,
                            'content': "",
                            'images': [],
                            'md5': metadata.get('md5'),
                            'created_at': metadata.get('created_at')
                        }
                        doc_md5 = metadata.get('md5')
                    chunk_count += 1
                    full_content.append(content)

                    # 从 metadata 中取出该 chunk 关联的图片文件名列表，
                    # 拼接成可供前端直接请求的 URL 路径（由 knowledge_router 中的图片路由处理）
                    image_paths = metadata.get('image_paths', [])
                    chunk_images = []
                    if isinstance(image_paths, list):
                        for img_name in image_paths:
                            img_url = f"/knowledge/image/{doc_md5}/{img_name}"
                            all_images.add(img_url)
                            chunk_images.append(img_url)

                    chunks.append({
                        'chunk_id': doc_id,
                        'index': len(chunks),
                        'content': content,
                        'page': metadata.get('page'),
                        'images': chunk_images,
                    })

            if doc_info:
                doc_info['chunk_count'] = chunk_count
                doc_info['content'] = '\n'.join(full_content)
                doc_info['images'] = sorted(all_images)
                doc_info['chunks'] = chunks

            logger.info(f"【向量数据库】获取文档详情: {filename}，chunk数量: {chunk_count}，图片数量: {len(all_images)}")
            return doc_info

        except Exception as e:
            logger.error(f"【向量数据库】获取文档详情 {filename} 时出错: {e}")
            raise

    async def get_document_chunks(self, user_id: str, filename: str):
        """
        获取文档的所有切片信息
        :param user_id: 用户ID
        :param filename: 文件名
        :return: 切片列表信息，包含图片列表
        """
        try:
            where_clause = {"user_id": user_id}
            store = await self.get_user_rag_store(user_id)
            all_docs = await asyncio.to_thread(
                store.get,
                include=['documents', 'metadatas'],
                where=where_clause
            )

            chunks = []
            chunk_index = 0

            for i, doc_id in enumerate(all_docs['ids']):
                metadata = all_docs['metadatas'][i] if i < len(all_docs['metadatas']) else {}
                content = all_docs['documents'][i] if i < len(all_docs['documents']) else ""

                source = metadata.get('source', metadata.get('filename', ''))
                if isinstance(source, str):
                    source_name = os.path.basename(source)
                else:
                    source_name = str(source)
                original_filename = metadata.get('original_filename', '')

                if source_name == filename or original_filename == filename:
                    doc_md5 = metadata.get('md5', '')
                    # 解析图片路径：从 metadata 中拿到图片文件名列表，拼接为前端可用的API URL
                    image_paths = metadata.get('image_paths', [])
                    if isinstance(image_paths, list):
                        images = [f"/knowledge/image/{doc_md5}/{img}" for img in image_paths]
                    else:
                        images = []

                    chunks.append({
                        'chunk_id': doc_id,
                        'index': chunk_index,
                        'content': content,
                        'metadata': metadata,
                        'images': images,
                    })
                    chunk_index += 1

            result = {
                'filename': filename,
                'total_chunks': len(chunks),
                'chunks': chunks
            }

            logger.info(f"【向量数据库】获取文档切片: {filename}，共 {len(chunks)} 个切片")
            return result

        except Exception as e:
            logger.error(f"【向量数据库】获取文档切片 {filename} 时出错: {e}")
            raise

    # 以下方法将参数透传给 DocumentProcessor，使其能获取 md5 和 user_id 用于多模态PDF加载
    async def get_file_document(self, read_path: str, md5: str = None, user_id: str = None) -> list[Document]:
        return await self.document_processor.get_file_document(read_path, md5, user_id)

    def get_file_document_sync(self, read_path: str, md5: str = None, user_id: str = None) -> list[Document]:
        return self.document_processor.get_file_document_sync(read_path, md5, user_id)

    def split_documents_sync(self, documents: list[Document]) -> list[Document]:
        return self.document_processor.split_documents_sync(documents)

    async def get_document(self, files: list = None, user_id: str = None, progress_callback=None):
        await self.document_processor.get_document(files, user_id, progress_callback)


if __name__ == '__main__':
    async def main():
        store = VectorStoreService()
        await store.get_document()

        retriever = await store.get_retriever()
        results = await retriever.ainvoke('扫地')
        print(f"检索结果数量: {len(results)}")
        for result in results:
            print(result)

    asyncio.run(main())
