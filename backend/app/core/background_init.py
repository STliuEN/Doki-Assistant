import asyncio
import time

from app.core.logger_handler import logger


class _BackgroundInitManager:
    """后台初始化管理器

    在 FastAPI 启动后通过 start() 在后台异步初始化所有重型资源，
    避免模块级导入阻塞 uvicorn 启动。
    每个组件初始化完成后设置对应的 Event。
    """

    def __init__(self):
        self._started = False
        self._start_time = 0.0

        # 各组件的初始化状态事件
        self.models_ready = asyncio.Event()
        self.note_service_ready = asyncio.Event()
        # Terminal state for NoteService initialization, including failure.
        self.note_service_init_done = asyncio.Event()
        self.reranker_ready = asyncio.Event()

        # 初始化后的实例（初始化完成前为 None）
        self.chat_model = None
        self.embed_model = None
        self.vision_model = None
        self.note_service = None
        self.reorder_service = None
        self.note_service_error = None

    async def start(self):
        """启动后台初始化（不阻塞主事件循环）"""
        if self._started:
            return
        self._started = True
        self._start_time = time.time()
        asyncio.create_task(self._initialize_all())

    async def _initialize_all(self):
        """后台执行所有重型初始化"""
        logger.info("🔄 开始后台初始化...")

        try:
            # 1. AI 模型（调用 factory 中的工厂类）
            await self._init_models()
        except Exception as e:
            self.note_service = None
            self.note_service_error = f"model initialization failed: {str(e)[:400]}"
            self.note_service_init_done.set()
            logger.error(f"❌ 模型后台初始化失败: {e}", exc_info=True)
            return

        try:
            # 2. ChromaDB projection（NoteService，依赖 embed_model）
            await self._init_note_service()
        except Exception as e:
            self.note_service = None
            self.note_service_error = str(e)[:500]
            logger.error(
                "❌ Chroma projection 初始化失败；核心 API 保持存活，向量功能进入 degraded 状态: %s",
                e,
                exc_info=True,
            )
        finally:
            # This event means initialization reached a terminal state; the
            # dependency checks note_service_error after waking up.
            self.note_service_init_done.set()

        # 3. 重排序模型不依赖 Chroma readiness，单独初始化。
        await self._init_reranker()

        elapsed = time.time() - self._start_time
        logger.info(f"✅ 后台初始化流程结束，耗时 {elapsed:.1f} 秒")

    async def _init_models(self):
        """初始化 AI 模型"""
        from app.utils.factory import ChatModelFactory, EmbedModelFactory, VisionModelFactory

        self.chat_model = await asyncio.to_thread(
            lambda: ChatModelFactory().generator()
        )
        logger.info("✅ chat_model 初始化完成")

        self.embed_model = await asyncio.to_thread(
            lambda: EmbedModelFactory().generator()
        )
        logger.info("✅ embed_model 初始化完成")

        # 预热意图路由：预建语义索引 + 预加载/计算阈值，让首个请求前就备好。
        # 切换 embedding 模型时随之换上对应的已调阈值（命中磁盘缓存）。
        from app.agent.intent_router import warmup_routing
        await warmup_routing()

        self.vision_model = await asyncio.to_thread(
            lambda: VisionModelFactory().generator()
        )
        logger.info("✅ vision_model 初始化完成")

        self.models_ready.set()

    async def _init_note_service(self):
        """初始化 NoteService（ChromaDB，依赖 embed_model）"""
        await self.models_ready.wait()

        from app.services.note_service import NoteService

        self.note_service = await asyncio.to_thread(
            lambda: NoteService(embed_model=self.embed_model)
        )
        self.note_service_error = None
        logger.info("✅ NoteService（ChromaDB）初始化完成")
        self.note_service_ready.set()

    async def _init_reranker(self):
        """检查并初始化重排序模型（触发 torch 等重型框架加载）"""
        from app.rag.reorder_service import ReorderService

        self.reorder_service = ReorderService()
        try:
            await self.reorder_service.warmup()
            logger.info("✅ 重排序模型预热完成")
        except Exception as e:
            logger.error(f"❌ 重排序模型预热失败，将在检索链路中跳过重排序: {e}", exc_info=True)

        logger.info("✅ ReorderService 初始化完成")
        self.reranker_ready.set()


# 全局单例
init_manager = _BackgroundInitManager()
