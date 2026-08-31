-- MySQL dump 10.13  Distrib 8.4.11, for Linux (x86_64)
--
-- Host: 127.0.0.1    Database: doki_e2
-- ------------------------------------------------------
-- Server version	8.4.11

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `alembic_version`
--

DROP TABLE IF EXISTS `alembic_version`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alembic_version`
--

LOCK TABLES `alembic_version` WRITE;
/*!40000 ALTER TABLE `alembic_version` DISABLE KEYS */;
INSERT INTO `alembic_version` VALUES ('20260828_0005_rag_skill');
/*!40000 ALTER TABLE `alembic_version` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `audit_events`
--

DROP TABLE IF EXISTS `audit_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `audit_events` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `actor_type` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `actor_id` varchar(64) DEFAULT NULL,
  `actor_role` varchar(64) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `action` varchar(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `target_type` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `target_id` varchar(64) DEFAULT NULL,
  `scope_type` varchar(32) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `scope_id` varchar(64) DEFAULT NULL,
  `policy_revision` bigint DEFAULT NULL,
  `subject_revision` bigint DEFAULT NULL,
  `content_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `before_json` json DEFAULT NULL,
  `after_json` json DEFAULT NULL,
  `grant_diff_json` json DEFAULT NULL,
  `reason` varchar(4096) NOT NULL,
  `effective_at` datetime(6) DEFAULT NULL,
  `expires_at` datetime(6) DEFAULT NULL,
  `result` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `error_code` varchar(64) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `correlation_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `run_id` varchar(64) DEFAULT NULL,
  `job_id` char(36) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `import_id` varchar(64) DEFAULT NULL,
  `migration_id` varchar(64) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `ix_audit_events_correlation_created` (`correlation_id`,`created_at`),
  KEY `ix_audit_events_job_created` (`job_id`,`created_at`),
  KEY `ix_audit_events_target_created` (`target_type`,`target_id`,`created_at`),
  KEY `ix_audit_events_actor_created` (`actor_type`,`actor_id`,`created_at`),
  CONSTRAINT `audit_events_ibfk_1` FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_audit_events_id_uuid` CHECK (regexp_like(`id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `audit_events`
--

LOCK TABLES `audit_events` WRITE;
/*!40000 ALTER TABLE `audit_events` DISABLE KEYS */;
INSERT INTO `audit_events` VALUES ('0043ee11-e8b6-440e-bd8b-ca981285d03f','system',NULL,NULL,'job.succeeded','job','8fa937ba-8f77-47cd-9cd6-129ffff460dc',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1, \"result_digest\": \"b56e9f9de5f727d0b414a28792cb584f5b788ef31eb74c7fed148ef5a23fff7a\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'4867c5a6-adc2-4752-891d-c031b8f3d6b9',NULL,'8fa937ba-8f77-47cd-9cd6-129ffff460dc',NULL,NULL,'2026-08-28 09:06:27.345056'),('0200e4f2-8cbe-42ba-9840-c84d64006944','system',NULL,NULL,'job.started','job','ad4debac-1ef3-40dc-b45e-a58f4797b363',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'3a779de4-dcb9-4bb0-9452-ee80d5f299a9',NULL,'ad4debac-1ef3-40dc-b45e-a58f4797b363',NULL,NULL,'2026-08-28 09:02:41.595278'),('03b0af6d-93df-4c33-b564-1369df2b8985','system',NULL,NULL,'job.succeeded','job','a8e99039-8b40-4a9e-9853-968f9c0f6b15',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2, \"result_digest\": \"93105a2e0623d5c1c6d9054effed3165e3f350748c3a7163a620e2f38cb03756\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'f1cd4859-7128-4ded-84de-11a847f905a4',NULL,'a8e99039-8b40-4a9e-9853-968f9c0f6b15',NULL,NULL,'2026-08-28 09:06:32.204631'),('0492f036-74ec-4c0f-a6e3-fcc9e41b566f','system',NULL,NULL,'job.started','job','7fdfb197-f345-4864-a59c-4d2e787f3a4b',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'54d1b008-af26-4a88-b570-dfd4145cc982',NULL,'7fdfb197-f345-4864-a59c-4d2e787f3a4b',NULL,NULL,'2026-08-28 08:50:01.179622'),('04e2c38b-0809-4871-85f3-26f2161a6651','system',NULL,NULL,'job.lease_expired','job','8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"leased\", \"fencing_token\": 1}','{\"status\": \"retry_wait\"}',NULL,'lease expired and SQL state was recovered',NULL,NULL,'retry_wait','lease_expired','26224654-9f6b-4861-a1e1-3ca4cbd6f710',NULL,'8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',NULL,NULL,'2026-08-28 08:50:06.823716'),('086b64ff-e0e5-48a3-9e70-541898dc4cd0','system',NULL,NULL,'job.started','job','b05c9ec6-98bb-45d8-ba5f-d0831c19f541',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2}',NULL,'leased handler started',NULL,NULL,'running',NULL,'ef27f62b-ae9c-45d1-8c25-37bd454109a6',NULL,'b05c9ec6-98bb-45d8-ba5f-d0831c19f541',NULL,NULL,'2026-08-28 09:14:49.842053'),('0ffc3ab1-eb80-4c4b-be1b-ef86c3c247d8','system',NULL,NULL,'job.started','job','453a662e-c61c-45ed-843f-1677589f79c4',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2}',NULL,'leased handler started',NULL,NULL,'running',NULL,'568738ea-af5f-49d2-b2f3-f9edd845fc92',NULL,'453a662e-c61c-45ed-843f-1677589f79c4',NULL,NULL,'2026-08-28 09:13:02.770867'),('10d5e123-e192-47a2-931d-aba4739bcdc3','system',NULL,NULL,'job.claimed','job','e8536c74-76ab-4356-bb60-7075a7692e22',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'990d1c8e-3278-4275-87d0-57228c1e8c63',NULL,'e8536c74-76ab-4356-bb60-7075a7692e22',NULL,NULL,'2026-08-28 09:02:41.805817'),('11385a51-bdfe-44ba-bdf5-0a68c1006680','system',NULL,NULL,'job.claimed','job','7da7ac7e-ad14-4056-acae-d621701fab8e',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'07125c6e-d8ec-4f66-bdbd-5c31ac00e213',NULL,'7da7ac7e-ad14-4056-acae-d621701fab8e',NULL,NULL,'2026-08-28 08:50:40.894264'),('11b4ef0d-30f1-4600-b020-7586cdb82c76','system',NULL,NULL,'job.succeeded','job','71bec3d9-fd1b-42c7-b568-1d4cd89a7187',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2, \"result_digest\": \"93105a2e0623d5c1c6d9054effed3165e3f350748c3a7163a620e2f38cb03756\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'5a5b0403-0ebb-4779-a4b4-2a52ad088633',NULL,'71bec3d9-fd1b-42c7-b568-1d4cd89a7187',NULL,NULL,'2026-08-28 08:53:14.168255'),('13a17ca0-d02b-4913-9850-7c45d29b0569','system',NULL,NULL,'job.started','job','c3e8650c-22e9-41b5-a97e-dee5e4af8368',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2}',NULL,'leased handler started',NULL,NULL,'running',NULL,'bf52915c-3455-44bb-9875-34f531281cb7',NULL,'c3e8650c-22e9-41b5-a97e-dee5e4af8368',NULL,NULL,'2026-08-28 09:02:47.733107'),('13ab4866-ceaa-4791-9adb-04716f1bced2','system',NULL,NULL,'job.started','job','71bec3d9-fd1b-42c7-b568-1d4cd89a7187',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'5a5b0403-0ebb-4779-a4b4-2a52ad088633',NULL,'71bec3d9-fd1b-42c7-b568-1d4cd89a7187',NULL,NULL,'2026-08-28 08:53:09.151928'),('17f95000-20bd-4a92-ae62-82767fb702d0','system',NULL,NULL,'job.started','job','f05e5c5b-e702-4a7c-8e5b-8849e018a805',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'e554f8cb-b6e4-47e4-9e52-6895b01c13f4',NULL,'f05e5c5b-e702-4a7c-8e5b-8849e018a805',NULL,NULL,'2026-08-28 09:14:44.404160'),('1954e97d-417e-4e67-95b8-0ed850aa5687','system',NULL,NULL,'job.cancel_requested','job','4806906c-559b-49aa-b418-2834f5d19559',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"running\"}','{\"status\": \"cancel_requested\"}',NULL,'synthetic live cancellation',NULL,NULL,'cancel_requested',NULL,'9329167e-929a-4dab-9974-b8894fdfb097',NULL,'4806906c-559b-49aa-b418-2834f5d19559',NULL,NULL,'2026-08-28 08:53:09.373460'),('1a927b18-5c6f-4f93-a4df-97d65663b482','system',NULL,NULL,'job.claimed','job','40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'bbda1cee-17ec-4b71-96aa-714633a8f64b',NULL,'40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',NULL,NULL,'2026-08-28 08:50:01.595506'),('1ab67b75-d3e9-4fb9-b897-905dbd741940','system',NULL,NULL,'job.enqueued','job','8bc7774a-bb4b-4b70-87fa-1c50e1d9e803','e2-live','e2-live-1787907001',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"4f30e231ae41e716923ef480d9bf7309a628bb0795bfa34265737ef6beec8941\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'26224654-9f6b-4861-a1e1-3ca4cbd6f710',NULL,'8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',NULL,NULL,'2026-08-28 08:50:06.800632'),('1b991b01-82eb-4dd0-9e77-af5e3b9acb14','system',NULL,NULL,'job.dead_letter','job','d8934d75-9a75-40e5-b24f-6bc7337cb3d4',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'dead_letter','unknown_job_type','f1a78fda-2d8c-40c4-ba70-bb0dd23fe20b',NULL,'d8934d75-9a75-40e5-b24f-6bc7337cb3d4',NULL,NULL,'2026-08-28 08:53:08.945188'),('1c69f5e9-7cd2-44ac-bc6d-3d0729a9db2c','system',NULL,NULL,'job.enqueued','job','3b05aadf-8c73-45f5-a5c4-58a6e9f49869','e2-live','e2-live-1787907001',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"34e07b5a8b614f9f38103a34c9d1ab89b5dc0d4e109face7c5008f940144c3ff\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'d1a64cef-bcf8-4d8b-b171-31d7a6c107be',NULL,'3b05aadf-8c73-45f5-a5c4-58a6e9f49869',NULL,NULL,'2026-08-28 08:50:01.157541'),('1c98b3ff-8e9d-48a0-b9ed-55f1b5740cfd','system',NULL,NULL,'job.lease_expired','job','c3e8650c-22e9-41b5-a97e-dee5e4af8368',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"leased\", \"fencing_token\": 1}','{\"status\": \"retry_wait\"}',NULL,'lease expired and SQL state was recovered',NULL,NULL,'retry_wait','lease_expired','bf52915c-3455-44bb-9875-34f531281cb7',NULL,'c3e8650c-22e9-41b5-a97e-dee5e4af8368',NULL,NULL,'2026-08-28 09:02:47.718193'),('1cca729c-92c7-4085-be00-466c85903ab9','system',NULL,NULL,'job.cancelled','job','3eebd495-227e-42fa-bbb6-9d6f0af097cc',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"queued\"}','{\"status\": \"cancelled\"}',NULL,'failed live probe fixture cleanup',NULL,NULL,'cancelled',NULL,'4da191b1-a36b-436c-8cd1-f3d445a6e85e',NULL,'3eebd495-227e-42fa-bbb6-9d6f0af097cc',NULL,NULL,'2026-08-28 09:05:23.899723'),('1cd685f2-4abb-4d0e-8d2d-c3162b452b33','system',NULL,NULL,'job.enqueued','job','cdf1cc2a-9914-4041-bffa-d1ca7ba8cbe4','e2-live','e2-live-1787907188',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"30d268b0236cff446ae4b96b861bd81d01a402550c20501ce303d6d02d0d4611\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'c53a45e4-e645-458e-937f-d359929b0ec3',NULL,'cdf1cc2a-9914-4041-bffa-d1ca7ba8cbe4',NULL,NULL,'2026-08-28 08:53:08.442336'),('227613aa-0825-4dc8-a601-f0c75b84a651','system',NULL,NULL,'job.started','job','71bec3d9-fd1b-42c7-b568-1d4cd89a7187',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2}',NULL,'leased handler started',NULL,NULL,'running',NULL,'5a5b0403-0ebb-4779-a4b4-2a52ad088633',NULL,'71bec3d9-fd1b-42c7-b568-1d4cd89a7187',NULL,NULL,'2026-08-28 08:53:14.157001'),('23e0bc25-ada6-42d1-9bb7-2ab080774518','system',NULL,NULL,'job.claimed','job','4f8a8ecc-a8a0-49f0-9b78-ea8980ef929f',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'ea1a97e9-9d0d-4eff-9317-186e91ca1cbb',NULL,'4f8a8ecc-a8a0-49f0-9b78-ea8980ef929f',NULL,NULL,'2026-08-28 09:14:43.741151'),('257d2d05-9f40-438d-83b2-71724057e190','system',NULL,NULL,'job.claimed','job','4806906c-559b-49aa-b418-2834f5d19559',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'9329167e-929a-4dab-9974-b8894fdfb097',NULL,'4806906c-559b-49aa-b418-2834f5d19559',NULL,NULL,'2026-08-28 08:53:09.359386'),('27a60260-06c9-482d-a57a-a7530c20d594','system',NULL,NULL,'job.dead_letter','job','7da7ac7e-ad14-4056-acae-d621701fab8e',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'dead_letter','unknown_job_type','07125c6e-d8ec-4f66-bdbd-5c31ac00e213',NULL,'7da7ac7e-ad14-4056-acae-d621701fab8e',NULL,NULL,'2026-08-28 08:50:40.911730'),('27c10263-148d-463d-82d1-9269150032bc','system',NULL,NULL,'job.succeeded','job','40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2, \"result_digest\": \"93105a2e0623d5c1c6d9054effed3165e3f350748c3a7163a620e2f38cb03756\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'bbda1cee-17ec-4b71-96aa-714633a8f64b',NULL,'40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',NULL,NULL,'2026-08-28 08:50:06.219410'),('28b5757f-8bce-4613-9192-6ec9fb1280cb','system',NULL,NULL,'job.claimed','job','1f2e3e65-5a51-4187-a33d-de8f12e36305',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'dc557fc6-db88-4021-a465-3d7824b61ceb',NULL,'1f2e3e65-5a51-4187-a33d-de8f12e36305',NULL,NULL,'2026-08-28 08:50:40.430743'),('2b5a8b2b-cf22-4d14-bdfe-b2ca401703b0','system',NULL,NULL,'job.started','job','1f2e3e65-5a51-4187-a33d-de8f12e36305',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'dc557fc6-db88-4021-a465-3d7824b61ceb',NULL,'1f2e3e65-5a51-4187-a33d-de8f12e36305',NULL,NULL,'2026-08-28 08:50:40.441757'),('2c5bb812-4010-44d9-a566-28b1b3380f1a','system',NULL,NULL,'job.claimed','job','6dbbe917-0a7b-414c-8093-85be64438425',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'2ab25bb0-cb69-469b-84ac-12fc3f014e6b',NULL,'6dbbe917-0a7b-414c-8093-85be64438425',NULL,NULL,'2026-08-28 08:53:15.249111'),('2f903213-eb32-44e9-b429-f57c3047bd5d','system',NULL,NULL,'job.succeeded','job','6acbc215-969e-40f4-a246-e24c2b5fa6bb',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2, \"result_digest\": \"a4034c0dd4380bf6a870e4d8315ebc314576a40778f7c89c0e7d3a0f0f54fc76\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'000f885d-6dae-4e91-bbe0-a225f1aa42d6',NULL,'6acbc215-969e-40f4-a246-e24c2b5fa6bb',NULL,NULL,'2026-08-28 08:53:14.776703'),('30b03d63-95a1-4d7f-8763-eb6b87e957d0','system',NULL,NULL,'job.enqueued','job','b05c9ec6-98bb-45d8-ba5f-d0831c19f541','e2-live','e2-live-1787908484',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"4f30e231ae41e716923ef480d9bf7309a628bb0795bfa34265737ef6beec8941\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'ef27f62b-ae9c-45d1-8c25-37bd454109a6',NULL,'b05c9ec6-98bb-45d8-ba5f-d0831c19f541',NULL,NULL,'2026-08-28 09:14:49.805020'),('31915dd5-c5dc-4ce1-8c86-1cc2f03c185b','system',NULL,NULL,'job.enqueued','job','7da7ac7e-ad14-4056-acae-d621701fab8e','e2-live','e2-live-1787907041',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"073fd96e2966d29f69cbbf3303aeb53f654eab14bab37acb1c7e04a52b85ddd3\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'07125c6e-d8ec-4f66-bdbd-5c31ac00e213',NULL,'7da7ac7e-ad14-4056-acae-d621701fab8e',NULL,NULL,'2026-08-28 08:50:40.402542'),('31bba089-32a3-4ce7-b93e-a3daa3a53e53','system',NULL,NULL,'job.claimed','job','cb52ec86-33a8-4740-b5be-ada42af7d936',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'20cf0f20-8335-45e4-a90c-2806aea620bd',NULL,'cb52ec86-33a8-4740-b5be-ada42af7d936',NULL,NULL,'2026-08-28 09:14:50.319051'),('31fb0e07-430e-448d-862b-97fe003af9fb','system',NULL,NULL,'job.claimed','job','a8e99039-8b40-4a9e-9853-968f9c0f6b15',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 2, \"fencing_token\": 2}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'f1cd4859-7128-4ded-84de-11a847f905a4',NULL,'a8e99039-8b40-4a9e-9853-968f9c0f6b15',NULL,NULL,'2026-08-28 09:06:32.186009'),('337d7f5a-2318-4c2a-9540-239219c85dd5','system',NULL,NULL,'job.succeeded','job','b20b2caa-4963-4001-9498-940e2ed50536',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1, \"result_digest\": \"b56e9f9de5f727d0b414a28792cb584f5b788ef31eb74c7fed148ef5a23fff7a\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'9af42a37-9d9f-45e3-813c-33b3d0a78e11',NULL,'b20b2caa-4963-4001-9498-940e2ed50536',NULL,NULL,'2026-08-28 08:50:40.682370'),('34087b41-5651-43c7-ac30-c38213b91ef7','system',NULL,NULL,'job.claimed','job','e250124f-ce80-4060-b4f8-4ed7bfebc64c',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'2fdd0ab9-20a1-48c3-9894-b533bbac5ad2',NULL,'e250124f-ce80-4060-b4f8-4ed7bfebc64c',NULL,NULL,'2026-08-28 08:50:41.310821'),('343b81ce-bcff-4a7d-8b0e-a1bf566cead6','system',NULL,NULL,'job.enqueued','job','223f5b9c-0c2d-4c2e-826e-b2f520bc0f4b','e2-pressure','e2-live-1787907001',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"681ef90839c6f897325c95239268c45f29fb4d23ae63b7fc1f1bb7e37c46f0ed\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'7b9b1a01-58af-499a-864c-a6c21812cffd',NULL,'223f5b9c-0c2d-4c2e-826e-b2f520bc0f4b',NULL,NULL,'2026-08-28 08:50:06.853164'),('344a47ec-b4ad-40ea-aeb9-b7ac920d5d01','system',NULL,NULL,'job.started','job','cdf1cc2a-9914-4041-bffa-d1ca7ba8cbe4',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'c53a45e4-e645-458e-937f-d359929b0ec3',NULL,'cdf1cc2a-9914-4041-bffa-d1ca7ba8cbe4',NULL,NULL,'2026-08-28 08:53:08.706006'),('3695ce7e-b435-4655-a188-eb272c1733e5','system',NULL,NULL,'job.claimed','job','8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 2, \"fencing_token\": 2}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'26224654-9f6b-4861-a1e1-3ca4cbd6f710',NULL,'8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',NULL,NULL,'2026-08-28 08:50:06.827517'),('3798d9d8-8728-44f2-867b-d2bfa3e90865','system',NULL,NULL,'job.started','job','40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2}',NULL,'leased handler started',NULL,NULL,'running',NULL,'bbda1cee-17ec-4b71-96aa-714633a8f64b',NULL,'40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',NULL,NULL,'2026-08-28 08:50:06.208269'),('37a9f093-7bc7-4e4c-b3b5-6b65e4f08151','system',NULL,NULL,'job.lease_expired','job','dc02f5cc-8f3b-4217-b006-a4cae7699566',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"leased\", \"fencing_token\": 1}','{\"status\": \"retry_wait\"}',NULL,'lease expired and SQL state was recovered',NULL,NULL,'retry_wait','lease_expired','6eac776b-43da-45b3-bae7-8220b73eabaf',NULL,'dc02f5cc-8f3b-4217-b006-a4cae7699566',NULL,NULL,'2026-08-28 09:06:32.801443'),('38f19fe5-8494-4259-889d-59d8eaa73e14','system',NULL,NULL,'job.enqueued','job','1f2e3e65-5a51-4187-a33d-de8f12e36305','e2-live','e2-live-1787907001-restart',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"686a022a7f742e639e23453dd0ff416b67d70c3b1f24a9e1357076866c3068bb\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'dc557fc6-db88-4021-a465-3d7824b61ceb',NULL,'1f2e3e65-5a51-4187-a33d-de8f12e36305',NULL,NULL,'2026-08-28 08:50:06.932207'),('3d13fe95-d2d4-4bca-a2ec-f1c933503d94','system',NULL,NULL,'job.enqueued','job','6acbc215-969e-40f4-a246-e24c2b5fa6bb','e2-live','e2-live-1787907188',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"4f30e231ae41e716923ef480d9bf7309a628bb0795bfa34265737ef6beec8941\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'000f885d-6dae-4e91-bbe0-a225f1aa42d6',NULL,'6acbc215-969e-40f4-a246-e24c2b5fa6bb',NULL,NULL,'2026-08-28 08:53:14.738717'),('3e4ed065-7d7d-41c1-a185-db96a1e7f477','system',NULL,NULL,'job.dead_letter','job','1f2e3e65-5a51-4187-a33d-de8f12e36305',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'dead_letter','unknown_job_type','dc557fc6-db88-4021-a465-3d7824b61ceb',NULL,'1f2e3e65-5a51-4187-a33d-de8f12e36305',NULL,NULL,'2026-08-28 08:50:40.450525'),('3efc4ef3-ab8a-4c1b-914d-684af5058f2c','system',NULL,NULL,'job.started','job','5ffc8e31-43f5-43d6-9c45-75a34f526ef2',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'b83de93f-8297-4b36-be6d-eb8811669569',NULL,'5ffc8e31-43f5-43d6-9c45-75a34f526ef2',NULL,NULL,'2026-08-28 09:06:27.980064'),('40a04686-6dab-4635-a526-67d9276e2d4b','system',NULL,NULL,'job.claimed','job','dc02f5cc-8f3b-4217-b006-a4cae7699566',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'6eac776b-43da-45b3-bae7-8220b73eabaf',NULL,'dc02f5cc-8f3b-4217-b006-a4cae7699566',NULL,NULL,'2026-08-28 09:06:32.789015'),('4418642d-a481-4f93-a50b-917817dcf4c0','system',NULL,NULL,'job.claimed','job','8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'26224654-9f6b-4861-a1e1-3ca4cbd6f710',NULL,'8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',NULL,NULL,'2026-08-28 08:50:06.810494'),('4474a043-2b36-4ac8-8e9c-e7cd64756586','system',NULL,NULL,'job.cancelled','job','cb52ec86-33a8-4740-b5be-ada42af7d936',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"retry_wait\"}','{\"status\": \"cancelled\"}',NULL,'close abandoned E2 probe fixture after lease recovery',NULL,NULL,'cancelled',NULL,'20cf0f20-8335-45e4-a90c-2806aea620bd',NULL,'cb52ec86-33a8-4740-b5be-ada42af7d936',NULL,NULL,'2026-08-28 09:26:11.303536'),('45128a31-14e2-4ac2-838d-a18b9d3ffa65','system',NULL,NULL,'job.claimed','job','6acbc215-969e-40f4-a246-e24c2b5fa6bb',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'000f885d-6dae-4e91-bbe0-a225f1aa42d6',NULL,'6acbc215-969e-40f4-a246-e24c2b5fa6bb',NULL,NULL,'2026-08-28 08:53:14.746036'),('4cf90ef2-976d-4f6d-8602-9ff17abba2b5','system',NULL,NULL,'job.lease_expired','job','6acbc215-969e-40f4-a246-e24c2b5fa6bb',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"leased\", \"fencing_token\": 1}','{\"status\": \"retry_wait\"}',NULL,'lease expired and SQL state was recovered',NULL,NULL,'retry_wait','lease_expired','000f885d-6dae-4e91-bbe0-a225f1aa42d6',NULL,'6acbc215-969e-40f4-a246-e24c2b5fa6bb',NULL,NULL,'2026-08-28 08:53:14.758273'),('4edd183e-a5d4-4b2e-aaf7-fca9e36f854c','system',NULL,NULL,'job.cancel_requested','job','e250124f-ce80-4060-b4f8-4ed7bfebc64c',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"running\"}','{\"status\": \"cancel_requested\"}',NULL,'synthetic live cancellation',NULL,NULL,'cancel_requested',NULL,'2fdd0ab9-20a1-48c3-9894-b533bbac5ad2',NULL,'e250124f-ce80-4060-b4f8-4ed7bfebc64c',NULL,NULL,'2026-08-28 08:50:41.326861'),('53a5b2ad-f7f9-4bfd-b638-1e0308ad7fec','system',NULL,NULL,'job.enqueued','job','08e3e7a5-1557-42bb-a6db-622f7739417e','e2-live','e2-live-1787908484',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"073fd96e2966d29f69cbbf3303aeb53f654eab14bab37acb1c7e04a52b85ddd3\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'9fb8ce83-571c-47b4-98b3-44d0e9236e0b',NULL,'08e3e7a5-1557-42bb-a6db-622f7739417e',NULL,NULL,'2026-08-28 09:14:43.713627'),('53bebffe-6c45-4cfe-a6a7-c166550cb051','system',NULL,NULL,'job.started','job','434cfb34-fcc8-4c21-afa3-b426d715bbb6',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'5e508fa9-f644-41ba-bce2-3ff477a31ed7',NULL,'434cfb34-fcc8-4c21-afa3-b426d715bbb6',NULL,NULL,'2026-08-28 08:53:08.493239'),('55273fdc-4cce-473c-aab5-a470e64ec2a7','system',NULL,NULL,'job.started','job','6acbc215-969e-40f4-a246-e24c2b5fa6bb',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2}',NULL,'leased handler started',NULL,NULL,'running',NULL,'000f885d-6dae-4e91-bbe0-a225f1aa42d6',NULL,'6acbc215-969e-40f4-a246-e24c2b5fa6bb',NULL,NULL,'2026-08-28 08:53:14.773152'),('55521d2c-9963-4a62-93f4-c783f48cb1cb','system',NULL,NULL,'job.dead_letter','job','08e3e7a5-1557-42bb-a6db-622f7739417e',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'dead_letter','unknown_job_type','9fb8ce83-571c-47b4-98b3-44d0e9236e0b',NULL,'08e3e7a5-1557-42bb-a6db-622f7739417e',NULL,NULL,'2026-08-28 09:14:43.981198'),('566f6539-1bbd-4fa0-87a8-c515043f0750','system',NULL,NULL,'job.started','job','07e5fc05-e305-4281-9ae6-ec9cd26e576e',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'dada6dc4-4c38-45a4-abce-9e0d593fb250',NULL,'07e5fc05-e305-4281-9ae6-ec9cd26e576e',NULL,NULL,'2026-08-28 09:02:42.046542'),('57291696-59ff-4a36-828d-5914efde1869','system',NULL,NULL,'job.retry_wait','job','a8e99039-8b40-4a9e-9853-968f9c0f6b15',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'retry_wait','synthetic_retry','f1cd4859-7128-4ded-84de-11a847f905a4',NULL,'a8e99039-8b40-4a9e-9853-968f9c0f6b15',NULL,NULL,'2026-08-28 09:06:27.770870'),('577f2891-76f0-460e-ba85-773db3e48851','system',NULL,NULL,'job.enqueued','job','0076fb7a-4121-40ff-b01d-d174e8d91a7a','e2-pressure','e2-live-1787907986',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"681ef90839c6f897325c95239268c45f29fb4d23ae63b7fc1f1bb7e37c46f0ed\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'fe3d9afe-e99f-4b58-8249-75990660eb6b',NULL,'0076fb7a-4121-40ff-b01d-d174e8d91a7a',NULL,NULL,'2026-08-28 09:06:32.831634'),('579bfd49-10ce-4389-964f-73268bdca866','system',NULL,NULL,'job.started','job','07e5fc05-e305-4281-9ae6-ec9cd26e576e',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2}',NULL,'leased handler started',NULL,NULL,'running',NULL,'dada6dc4-4c38-45a4-abce-9e0d593fb250',NULL,'07e5fc05-e305-4281-9ae6-ec9cd26e576e',NULL,NULL,'2026-08-28 09:02:47.089784'),('58268819-7d6a-4d11-8e66-3766fad65f58','system',NULL,NULL,'job.enqueued','job','4f8a8ecc-a8a0-49f0-9b78-ea8980ef929f','e2-live','e2-live-1787908484',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"30d268b0236cff446ae4b96b861bd81d01a402550c20501ce303d6d02d0d4611\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'ea1a97e9-9d0d-4eff-9317-186e91ca1cbb',NULL,'4f8a8ecc-a8a0-49f0-9b78-ea8980ef929f',NULL,NULL,'2026-08-28 09:14:43.701314'),('59039de7-e05b-492c-967a-b9e105ce4b68','system',NULL,NULL,'job.claimed','job','b05c9ec6-98bb-45d8-ba5f-d0831c19f541',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'ef27f62b-ae9c-45d1-8c25-37bd454109a6',NULL,'b05c9ec6-98bb-45d8-ba5f-d0831c19f541',NULL,NULL,'2026-08-28 09:14:49.812037'),('59e01db1-4ab9-4c4c-9965-833397d0d2ab','system',NULL,NULL,'job.enqueued','job','453a662e-c61c-45ed-843f-1677589f79c4','e2-live','e2-live-1787907986-restart',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"686a022a7f742e639e23453dd0ff416b67d70c3b1f24a9e1357076866c3068bb\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'568738ea-af5f-49d2-b2f3-f9edd845fc92',NULL,'453a662e-c61c-45ed-843f-1677589f79c4',NULL,NULL,'2026-08-28 09:06:32.908691'),('5a99f854-da34-454e-9230-00575f763407','system',NULL,NULL,'job.enqueued','job','e8536c74-76ab-4356-bb60-7075a7692e22','e2-live','e2-live-1787907760',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"073fd96e2966d29f69cbbf3303aeb53f654eab14bab37acb1c7e04a52b85ddd3\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'990d1c8e-3278-4275-87d0-57228c1e8c63',NULL,'e8536c74-76ab-4356-bb60-7075a7692e22',NULL,NULL,'2026-08-28 09:02:41.556805'),('5b5f483e-d085-49fc-b2b6-e969dbdbf284','system',NULL,NULL,'job.claimed','job','5ffc8e31-43f5-43d6-9c45-75a34f526ef2',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'b83de93f-8297-4b36-be6d-eb8811669569',NULL,'5ffc8e31-43f5-43d6-9c45-75a34f526ef2',NULL,NULL,'2026-08-28 09:06:27.971617'),('5cfdc37e-94e9-4776-8957-c2a6c793c2df','system',NULL,NULL,'job.cancel_requested','job','3b05aadf-8c73-45f5-a5c4-58a6e9f49869',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"running\"}','{\"status\": \"cancel_requested\"}',NULL,'synthetic live cancellation',NULL,NULL,'cancel_requested',NULL,'d1a64cef-bcf8-4d8b-b171-31d7a6c107be',NULL,'3b05aadf-8c73-45f5-a5c4-58a6e9f49869',NULL,NULL,'2026-08-28 08:50:01.827834'),('5df037ea-5ba6-47bc-9d94-0f23502520b0','system',NULL,NULL,'job.lease_expired','job','cb52ec86-33a8-4740-b5be-ada42af7d936',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"running\", \"fencing_token\": 1}','{\"status\": \"retry_wait\"}',NULL,'lease expired and SQL state was recovered',NULL,NULL,'retry_wait','lease_expired','20cf0f20-8335-45e4-a90c-2806aea620bd',NULL,'cb52ec86-33a8-4740-b5be-ada42af7d936',NULL,NULL,'2026-08-28 09:26:11.292717'),('655c7374-0d18-4eff-979a-26d5c434c4e3','system',NULL,NULL,'job.claimed','job','c3e8650c-22e9-41b5-a97e-dee5e4af8368',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'bf52915c-3455-44bb-9875-34f531281cb7',NULL,'c3e8650c-22e9-41b5-a97e-dee5e4af8368',NULL,NULL,'2026-08-28 09:02:47.705158'),('67c62c69-6aa4-4ab5-a642-47975b19cc80','system',NULL,NULL,'job.started','job','d8934d75-9a75-40e5-b24f-6bc7337cb3d4',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'f1a78fda-2d8c-40c4-ba70-bb0dd23fe20b',NULL,'d8934d75-9a75-40e5-b24f-6bc7337cb3d4',NULL,NULL,'2026-08-28 08:53:08.936230'),('68670aa7-f232-4b7a-8fe7-a95d235d91b0','system',NULL,NULL,'job.enqueued','job','7fdfb197-f345-4864-a59c-4d2e787f3a4b','e2-live','e2-live-1787907001',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"30d268b0236cff446ae4b96b861bd81d01a402550c20501ce303d6d02d0d4611\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'54d1b008-af26-4a88-b570-dfd4145cc982',NULL,'7fdfb197-f345-4864-a59c-4d2e787f3a4b',NULL,NULL,'2026-08-28 08:50:01.127260'),('6af2aeeb-a942-4e84-81e2-cc11a655585a','system',NULL,NULL,'job.enqueued','job','6dbbe917-0a7b-414c-8093-85be64438425','e2-live','e2-live-1787907188-restart',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"686a022a7f742e639e23453dd0ff416b67d70c3b1f24a9e1357076866c3068bb\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'2ab25bb0-cb69-469b-84ac-12fc3f014e6b',NULL,'6dbbe917-0a7b-414c-8093-85be64438425',NULL,NULL,'2026-08-28 08:53:14.864285'),('6af42b78-ab49-4063-8544-55c9f9013af3','system',NULL,NULL,'job.cancelled','job','5ffc8e31-43f5-43d6-9c45-75a34f526ef2',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'cancelled','cancel_requested','b83de93f-8297-4b36-be6d-eb8811669569',NULL,'5ffc8e31-43f5-43d6-9c45-75a34f526ef2',NULL,NULL,'2026-08-28 09:06:27.999252'),('6b3a1fdf-1e01-40bf-9dd9-25174e9a0be1','system',NULL,NULL,'job.started','job','cb52ec86-33a8-4740-b5be-ada42af7d936',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'20cf0f20-8335-45e4-a90c-2806aea620bd',NULL,'cb52ec86-33a8-4740-b5be-ada42af7d936',NULL,NULL,'2026-08-28 09:14:50.332866'),('6b5ddba1-f6b7-4848-ae3e-6ba2b3741ba8','system',NULL,NULL,'job.dead_letter','job','e8536c74-76ab-4356-bb60-7075a7692e22',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'dead_letter','unknown_job_type','990d1c8e-3278-4275-87d0-57228c1e8c63',NULL,'e8536c74-76ab-4356-bb60-7075a7692e22',NULL,NULL,'2026-08-28 09:02:41.822188'),('6c29f052-bd22-4e5a-a802-30a0b78e10a5','system',NULL,NULL,'job.claimed','job','71bec3d9-fd1b-42c7-b568-1d4cd89a7187',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'5a5b0403-0ebb-4779-a4b4-2a52ad088633',NULL,'71bec3d9-fd1b-42c7-b568-1d4cd89a7187',NULL,NULL,'2026-08-28 08:53:09.143280'),('6cc441de-37c9-4d9c-96e8-9e953cb11fb4','system',NULL,NULL,'job.dead_letter','job','52aaa47f-33a3-4fd8-8132-1ff031232e70',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'dead_letter','unknown_job_type','82de4ba5-6024-4733-99a3-7d3b270bc537',NULL,'52aaa47f-33a3-4fd8-8132-1ff031232e70',NULL,NULL,'2026-08-28 08:50:01.410991'),('6d20416a-bf7e-49a4-880c-8bf07bed232e','system',NULL,NULL,'job.started','job','cb0c8ef3-b3ef-465d-937f-9560fa75b30d',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2}',NULL,'leased handler started',NULL,NULL,'running',NULL,'5c6811b3-3f89-4b75-b87f-747480e73fac',NULL,'cb0c8ef3-b3ef-465d-937f-9560fa75b30d',NULL,NULL,'2026-08-28 09:14:49.194006'),('6e6b61ba-4d8d-4f65-a9de-2a21ad667834','system',NULL,NULL,'job.started','job','8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2}',NULL,'leased handler started',NULL,NULL,'running',NULL,'26224654-9f6b-4861-a1e1-3ca4cbd6f710',NULL,'8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',NULL,NULL,'2026-08-28 08:50:06.838545'),('6eed3d91-8d38-43a1-9c2d-c79ddcd645d9','system',NULL,NULL,'job.started','job','b20b2caa-4963-4001-9498-940e2ed50536',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'9af42a37-9d9f-45e3-813c-33b3d0a78e11',NULL,'b20b2caa-4963-4001-9498-940e2ed50536',NULL,NULL,'2026-08-28 08:50:40.672294'),('6fa274d8-e2b6-4ad6-a8bc-ac2ee54e32ec','system',NULL,NULL,'job.cancelled','job','bdac56dc-a822-4da7-b44d-bc9a0c9a32e8',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'cancelled','cancel_requested','ae5e4fe9-fd6c-4f55-a3d5-c013b758b16f',NULL,'bdac56dc-a822-4da7-b44d-bc9a0c9a32e8',NULL,NULL,'2026-08-28 09:02:42.281058'),('70c1b145-77e5-47e0-ae01-347d63132e5a','system',NULL,NULL,'job.started','job','a8e99039-8b40-4a9e-9853-968f9c0f6b15',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2}',NULL,'leased handler started',NULL,NULL,'running',NULL,'f1cd4859-7128-4ded-84de-11a847f905a4',NULL,'a8e99039-8b40-4a9e-9853-968f9c0f6b15',NULL,NULL,'2026-08-28 09:06:32.193916'),('741676c7-3cd8-47b0-93b4-241c694c7443','system',NULL,NULL,'job.claimed','job','a8e99039-8b40-4a9e-9853-968f9c0f6b15',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'f1cd4859-7128-4ded-84de-11a847f905a4',NULL,'a8e99039-8b40-4a9e-9853-968f9c0f6b15',NULL,NULL,'2026-08-28 09:06:27.755371'),('7434b09e-f14d-4b81-9f32-0e61d7567c15','system',NULL,NULL,'job.claimed','job','07e5fc05-e305-4281-9ae6-ec9cd26e576e',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 2, \"fencing_token\": 2}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'dada6dc4-4c38-45a4-abce-9e0d593fb250',NULL,'07e5fc05-e305-4281-9ae6-ec9cd26e576e',NULL,NULL,'2026-08-28 09:02:47.081565'),('74ddc0ec-48a3-45a7-bbbf-e276151cfcbf','system',NULL,NULL,'job.succeeded','job','8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2, \"result_digest\": \"a4034c0dd4380bf6a870e4d8315ebc314576a40778f7c89c0e7d3a0f0f54fc76\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'26224654-9f6b-4861-a1e1-3ca4cbd6f710',NULL,'8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',NULL,NULL,'2026-08-28 08:50:06.842053'),('7572c073-948d-49bb-b40a-8efc4940fde9','system',NULL,NULL,'job.enqueued','job','37818753-632e-41e4-b680-31e9213beb77','e2-pressure','e2-live-1787907760',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"681ef90839c6f897325c95239268c45f29fb4d23ae63b7fc1f1bb7e37c46f0ed\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'834484d6-2ec1-47d0-b3cc-a413ba419a29',NULL,'37818753-632e-41e4-b680-31e9213beb77',NULL,NULL,'2026-08-28 09:02:47.749558'),('75b49119-d964-4396-9f90-a856ea88c3c8','system',NULL,NULL,'job.enqueued','job','2ba78a8c-6e99-45f1-b645-c0dc18bd455c','e2-pressure','e2-live-1787908484',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"681ef90839c6f897325c95239268c45f29fb4d23ae63b7fc1f1bb7e37c46f0ed\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'6c1e0052-5f90-416f-bcb6-a89b9b147968',NULL,'2ba78a8c-6e99-45f1-b645-c0dc18bd455c',NULL,NULL,'2026-08-28 09:14:49.857145'),('76a23af0-50bc-42c6-a2c4-bfdb64d2c751','system',NULL,NULL,'job.enqueued','job','8d723d99-797d-4084-854a-3a671b896635','e2-pressure','e2-live-1787907188',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"681ef90839c6f897325c95239268c45f29fb4d23ae63b7fc1f1bb7e37c46f0ed\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'68e8831c-12ec-423b-8b92-91f9c46c7d77',NULL,'8d723d99-797d-4084-854a-3a671b896635',NULL,NULL,'2026-08-28 08:53:14.787400'),('78aede13-3461-4538-a6a6-16ef01c57037','system',NULL,NULL,'job.started','job','453a662e-c61c-45ed-843f-1677589f79c4',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'568738ea-af5f-49d2-b2f3-f9edd845fc92',NULL,'453a662e-c61c-45ed-843f-1677589f79c4',NULL,NULL,'2026-08-28 09:06:33.296898'),('794e8c8f-75b2-409b-92d7-74f1a7c8b8d3','system',NULL,NULL,'job.succeeded','job','6dbbe917-0a7b-414c-8093-85be64438425',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2, \"result_digest\": \"fbca803246f03035e7309ca4f93538c1c955b4413200a6a0db8ffabc499dca11\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'2ab25bb0-cb69-469b-84ac-12fc3f014e6b',NULL,'6dbbe917-0a7b-414c-8093-85be64438425',NULL,NULL,'2026-08-28 09:00:32.990314'),('7a834ed5-2c04-46dc-a249-592592fa8b98','system',NULL,NULL,'job.cancelled','job','3b05aadf-8c73-45f5-a5c4-58a6e9f49869',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'cancelled','cancel_requested','d1a64cef-bcf8-4d8b-b171-31d7a6c107be',NULL,'3b05aadf-8c73-45f5-a5c4-58a6e9f49869',NULL,NULL,'2026-08-28 08:50:01.839163'),('7aeb8489-5b10-4096-b84f-75cc22d65329','system',NULL,NULL,'job.cancel_requested','job','bdac56dc-a822-4da7-b44d-bc9a0c9a32e8',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"running\"}','{\"status\": \"cancel_requested\"}',NULL,'synthetic live cancellation',NULL,NULL,'cancel_requested',NULL,'ae5e4fe9-fd6c-4f55-a3d5-c013b758b16f',NULL,'bdac56dc-a822-4da7-b44d-bc9a0c9a32e8',NULL,NULL,'2026-08-28 09:02:42.269525'),('7b13020d-24bd-4048-85ae-e227821d6f7b','system',NULL,NULL,'job.claimed','job','dc02f5cc-8f3b-4217-b006-a4cae7699566',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 2, \"fencing_token\": 2}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'6eac776b-43da-45b3-bae7-8220b73eabaf',NULL,'dc02f5cc-8f3b-4217-b006-a4cae7699566',NULL,NULL,'2026-08-28 09:06:32.805400'),('7ba2dc45-73f3-46f5-8294-b8e86aa8cfea','system',NULL,NULL,'job.started','job','dc02f5cc-8f3b-4217-b006-a4cae7699566',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2}',NULL,'leased handler started',NULL,NULL,'running',NULL,'6eac776b-43da-45b3-bae7-8220b73eabaf',NULL,'dc02f5cc-8f3b-4217-b006-a4cae7699566',NULL,NULL,'2026-08-28 09:06:32.816814'),('7fa00d8a-7452-4647-b369-0cb47f713b25','system',NULL,NULL,'job.cancelled','job','0076fb7a-4121-40ff-b01d-d174e8d91a7a',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"queued\"}','{\"status\": \"cancelled\"}',NULL,'synthetic backpressure cleanup',NULL,NULL,'cancelled',NULL,'fe3d9afe-e99f-4b58-8249-75990660eb6b',NULL,'0076fb7a-4121-40ff-b01d-d174e8d91a7a',NULL,NULL,'2026-08-28 09:06:32.835320'),('855fbd64-2c81-4db0-b73b-73974514b812','system',NULL,NULL,'job.enqueued','job','c3e8650c-22e9-41b5-a97e-dee5e4af8368','e2-live','e2-live-1787907760',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"4f30e231ae41e716923ef480d9bf7309a628bb0795bfa34265737ef6beec8941\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'bf52915c-3455-44bb-9875-34f531281cb7',NULL,'c3e8650c-22e9-41b5-a97e-dee5e4af8368',NULL,NULL,'2026-08-28 09:02:47.695735'),('881e8109-993b-461f-b5bf-e66b30547a26','system',NULL,NULL,'job.enqueued','job','434cfb34-fcc8-4c21-afa3-b426d715bbb6','e2-live','e2-live-1787907041',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"4f30e231ae41e716923ef480d9bf7309a628bb0795bfa34265737ef6beec8941\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'5e508fa9-f644-41ba-bce2-3ff477a31ed7',NULL,'434cfb34-fcc8-4c21-afa3-b426d715bbb6',NULL,NULL,'2026-08-28 08:50:46.693305'),('898846d2-c9f6-41a8-8a51-44ac1dd0d8c4','system',NULL,NULL,'job.enqueued','job','52aaa47f-33a3-4fd8-8132-1ff031232e70','e2-live','e2-live-1787907001',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"073fd96e2966d29f69cbbf3303aeb53f654eab14bab37acb1c7e04a52b85ddd3\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'82de4ba5-6024-4733-99a3-7d3b270bc537',NULL,'52aaa47f-33a3-4fd8-8132-1ff031232e70',NULL,NULL,'2026-08-28 08:50:01.139671'),('8ac10436-d50a-4185-8aba-b91b336aa3ef','system',NULL,NULL,'job.enqueued','job','71bec3d9-fd1b-42c7-b568-1d4cd89a7187','e2-live','e2-live-1787907188',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"8fbed32134bbef3538079dd3f443629eb3708208025344d24b6501b64edeec59\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'5a5b0403-0ebb-4779-a4b4-2a52ad088633',NULL,'71bec3d9-fd1b-42c7-b568-1d4cd89a7187',NULL,NULL,'2026-08-28 08:53:08.463496'),('8bc5f82f-c72a-484d-a97b-c6469c50c20f','system',NULL,NULL,'job.claimed','job','453a662e-c61c-45ed-843f-1677589f79c4',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 2, \"fencing_token\": 2}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'568738ea-af5f-49d2-b2f3-f9edd845fc92',NULL,'453a662e-c61c-45ed-843f-1677589f79c4',NULL,NULL,'2026-08-28 09:13:02.759342'),('8cb342d8-2a95-46e8-bb7b-7fcd49e39f05','system',NULL,NULL,'job.started','job','08e3e7a5-1557-42bb-a6db-622f7739417e',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'9fb8ce83-571c-47b4-98b3-44d0e9236e0b',NULL,'08e3e7a5-1557-42bb-a6db-622f7739417e',NULL,NULL,'2026-08-28 09:14:43.972828'),('8dc85906-2b44-42d8-8806-b9a5dff4f641','system',NULL,NULL,'job.claimed','job','cb0c8ef3-b3ef-465d-937f-9560fa75b30d',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 2, \"fencing_token\": 2}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'5c6811b3-3f89-4b75-b87f-747480e73fac',NULL,'cb0c8ef3-b3ef-465d-937f-9560fa75b30d',NULL,NULL,'2026-08-28 09:14:49.181622'),('8e5008ae-554c-4ac2-8b20-4b38679575a7','system',NULL,NULL,'job.claimed','job','3ee6574e-1e12-43f3-9d95-164f4bf33f10',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'4a43d51b-0c01-43a9-9f75-b048089a5de5',NULL,'3ee6574e-1e12-43f3-9d95-164f4bf33f10',NULL,NULL,'2026-08-28 08:50:41.094206'),('8e754183-8f58-412c-a8c7-4fcf5277ec92','system',NULL,NULL,'job.succeeded','job','dc02f5cc-8f3b-4217-b006-a4cae7699566',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2, \"result_digest\": \"a4034c0dd4380bf6a870e4d8315ebc314576a40778f7c89c0e7d3a0f0f54fc76\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'6eac776b-43da-45b3-bae7-8220b73eabaf',NULL,'dc02f5cc-8f3b-4217-b006-a4cae7699566',NULL,NULL,'2026-08-28 09:06:32.820487'),('93dbac8f-1fad-46da-a4ae-107cf29024b7','system',NULL,NULL,'job.claimed','job','5a220335-bdeb-4201-89a8-43b64de84159',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'ffb19ea3-e520-41f2-82b4-3d8cba768ae7',NULL,'5a220335-bdeb-4201-89a8-43b64de84159',NULL,NULL,'2026-08-28 09:06:27.554009'),('94d8bd13-0a01-44a8-875a-31532d45a2b1','system',NULL,NULL,'job.retry_wait','job','3ee6574e-1e12-43f3-9d95-164f4bf33f10',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'retry_wait','synthetic_retry','4a43d51b-0c01-43a9-9f75-b048089a5de5',NULL,'3ee6574e-1e12-43f3-9d95-164f4bf33f10',NULL,NULL,'2026-08-28 08:50:41.110456'),('94ed3f70-8799-4487-9a9d-cb71460b263f','system',NULL,NULL,'job.claimed','job','f05e5c5b-e702-4a7c-8e5b-8849e018a805',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'e554f8cb-b6e4-47e4-9e52-6895b01c13f4',NULL,'f05e5c5b-e702-4a7c-8e5b-8849e018a805',NULL,NULL,'2026-08-28 09:14:44.395929'),('961f7562-6863-4cb2-846a-3abd5c0bf930','system',NULL,NULL,'job.enqueued','job','5a220335-bdeb-4201-89a8-43b64de84159','e2-live','e2-live-1787907986',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"073fd96e2966d29f69cbbf3303aeb53f654eab14bab37acb1c7e04a52b85ddd3\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'ffb19ea3-e520-41f2-82b4-3d8cba768ae7',NULL,'5a220335-bdeb-4201-89a8-43b64de84159',NULL,NULL,'2026-08-28 09:06:27.298639'),('964835b5-2563-441e-9e41-0f1d2e44005e','system',NULL,NULL,'job.claimed','job','6acbc215-969e-40f4-a246-e24c2b5fa6bb',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 2, \"fencing_token\": 2}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'000f885d-6dae-4e91-bbe0-a225f1aa42d6',NULL,'6acbc215-969e-40f4-a246-e24c2b5fa6bb',NULL,NULL,'2026-08-28 08:53:14.762336'),('96eef697-cece-4092-9bac-70b12364d5ed','system',NULL,NULL,'job.cancel_requested','job','5ffc8e31-43f5-43d6-9c45-75a34f526ef2',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"running\"}','{\"status\": \"cancel_requested\"}',NULL,'synthetic live cancellation',NULL,NULL,'cancel_requested',NULL,'b83de93f-8297-4b36-be6d-eb8811669569',NULL,'5ffc8e31-43f5-43d6-9c45-75a34f526ef2',NULL,NULL,'2026-08-28 09:06:27.986455'),('974a27d6-71f9-4fae-bb22-25eb1a7c7ac0','system',NULL,NULL,'job.retry_wait','job','07e5fc05-e305-4281-9ae6-ec9cd26e576e',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'retry_wait','synthetic_retry','dada6dc4-4c38-45a4-abce-9e0d593fb250',NULL,'07e5fc05-e305-4281-9ae6-ec9cd26e576e',NULL,NULL,'2026-08-28 09:02:42.054485'),('976b9332-5255-477d-a49a-835c4302b2dc','system',NULL,NULL,'job.succeeded','job','434cfb34-fcc8-4c21-afa3-b426d715bbb6',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1, \"result_digest\": \"aa5b969be4d8f9db33152f23b13b92528ea22e5c130bd31c6506eaf9f6b0c967\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'5e508fa9-f644-41ba-bce2-3ff477a31ed7',NULL,'434cfb34-fcc8-4c21-afa3-b426d715bbb6',NULL,NULL,'2026-08-28 08:53:08.502639'),('97c07676-32a1-4295-9f03-2d4e090054af','system',NULL,NULL,'job.started','job','6dbbe917-0a7b-414c-8093-85be64438425',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'2ab25bb0-cb69-469b-84ac-12fc3f014e6b',NULL,'6dbbe917-0a7b-414c-8093-85be64438425',NULL,NULL,'2026-08-28 08:53:15.260196'),('9877981a-6ee8-4aee-9c20-b64d99cbf6bc','system',NULL,NULL,'job.succeeded','job','4f8a8ecc-a8a0-49f0-9b78-ea8980ef929f',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1, \"result_digest\": \"b56e9f9de5f727d0b414a28792cb584f5b788ef31eb74c7fed148ef5a23fff7a\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'ea1a97e9-9d0d-4eff-9317-186e91ca1cbb',NULL,'4f8a8ecc-a8a0-49f0-9b78-ea8980ef929f',NULL,NULL,'2026-08-28 09:14:43.760621'),('9b4d6c5a-097e-4730-a58e-d483f54f2d87','system',NULL,NULL,'job.cancel_requested','job','f05e5c5b-e702-4a7c-8e5b-8849e018a805',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"running\"}','{\"status\": \"cancel_requested\"}',NULL,'synthetic live cancellation',NULL,NULL,'cancel_requested',NULL,'e554f8cb-b6e4-47e4-9e52-6895b01c13f4',NULL,'f05e5c5b-e702-4a7c-8e5b-8849e018a805',NULL,NULL,'2026-08-28 09:14:44.411259'),('9cd11356-307d-4bbe-b0e0-57baaf4c0495','system',NULL,NULL,'job.enqueued','job','cb0c8ef3-b3ef-465d-937f-9560fa75b30d','e2-live','e2-live-1787908484',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"8fbed32134bbef3538079dd3f443629eb3708208025344d24b6501b64edeec59\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'5c6811b3-3f89-4b75-b87f-747480e73fac',NULL,'cb0c8ef3-b3ef-465d-937f-9560fa75b30d',NULL,NULL,'2026-08-28 09:14:43.722562'),('9d3bdaf4-332b-4e43-a142-ae426198f5bc','system',NULL,NULL,'job.claimed','job','52aaa47f-33a3-4fd8-8132-1ff031232e70',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'82de4ba5-6024-4733-99a3-7d3b270bc537',NULL,'52aaa47f-33a3-4fd8-8132-1ff031232e70',NULL,NULL,'2026-08-28 08:50:01.393742'),('9e4fc323-842b-4b57-aced-e9b42070513c','system',NULL,NULL,'job.lease_expired','job','b05c9ec6-98bb-45d8-ba5f-d0831c19f541',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"leased\", \"fencing_token\": 1}','{\"status\": \"retry_wait\"}',NULL,'lease expired and SQL state was recovered',NULL,NULL,'retry_wait','lease_expired','ef27f62b-ae9c-45d1-8c25-37bd454109a6',NULL,'b05c9ec6-98bb-45d8-ba5f-d0831c19f541',NULL,NULL,'2026-08-28 09:14:49.824452'),('9f8fe70c-ef60-452f-918a-a17c2781e326','system',NULL,NULL,'job.enqueued','job','a8e99039-8b40-4a9e-9853-968f9c0f6b15','e2-live','e2-live-1787907986',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"8fbed32134bbef3538079dd3f443629eb3708208025344d24b6501b64edeec59\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'f1cd4859-7128-4ded-84de-11a847f905a4',NULL,'a8e99039-8b40-4a9e-9853-968f9c0f6b15',NULL,NULL,'2026-08-28 09:06:27.306009'),('a055e510-2fe7-43b2-95cc-a2f7e8a22aa1','system',NULL,NULL,'job.started','job','40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'bbda1cee-17ec-4b71-96aa-714633a8f64b',NULL,'40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',NULL,NULL,'2026-08-28 08:50:01.603274'),('a2b4efed-0fd0-4fe2-b7f8-883c9cff9b56','system',NULL,NULL,'job.fenced_rejected','job','b05c9ec6-98bb-45d8-ba5f-d0831c19f541',NULL,NULL,NULL,NULL,NULL,'null','null',NULL,'stale lease rejected during succeed',NULL,NULL,'rejected','stale_fencing_token','ef27f62b-ae9c-45d1-8c25-37bd454109a6',NULL,'b05c9ec6-98bb-45d8-ba5f-d0831c19f541',NULL,NULL,'2026-08-28 09:14:49.838422'),('a48cf024-cb64-4d87-8183-95945a19beaf','system',NULL,NULL,'job.claimed','job','40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 2, \"fencing_token\": 2}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'bbda1cee-17ec-4b71-96aa-714633a8f64b',NULL,'40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',NULL,NULL,'2026-08-28 08:50:06.199549'),('a4c7fb91-c936-4353-9091-3f3e743d5126','system',NULL,NULL,'job.started','job','a8e99039-8b40-4a9e-9853-968f9c0f6b15',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'f1cd4859-7128-4ded-84de-11a847f905a4',NULL,'a8e99039-8b40-4a9e-9853-968f9c0f6b15',NULL,NULL,'2026-08-28 09:06:27.762949'),('a623a7d3-7d7b-4f64-a0e2-0163455a5989','system',NULL,NULL,'job.succeeded','job','c3e8650c-22e9-41b5-a97e-dee5e4af8368',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2, \"result_digest\": \"a4034c0dd4380bf6a870e4d8315ebc314576a40778f7c89c0e7d3a0f0f54fc76\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'bf52915c-3455-44bb-9875-34f531281cb7',NULL,'c3e8650c-22e9-41b5-a97e-dee5e4af8368',NULL,NULL,'2026-08-28 09:02:47.736943'),('a69371a9-ba27-4ef6-8b85-1e104b3b2a08','system',NULL,NULL,'job.lease_expired','job','453a662e-c61c-45ed-843f-1677589f79c4',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"running\", \"fencing_token\": 1}','{\"status\": \"retry_wait\"}',NULL,'lease expired and SQL state was recovered',NULL,NULL,'retry_wait','lease_expired','568738ea-af5f-49d2-b2f3-f9edd845fc92',NULL,'453a662e-c61c-45ed-843f-1677589f79c4',NULL,NULL,'2026-08-28 09:12:22.595169'),('a864f08f-3b32-4d10-87ab-49c765a8691a','system',NULL,NULL,'job.claimed','job','453a662e-c61c-45ed-843f-1677589f79c4',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'568738ea-af5f-49d2-b2f3-f9edd845fc92',NULL,'453a662e-c61c-45ed-843f-1677589f79c4',NULL,NULL,'2026-08-28 09:06:33.285859'),('a8f34177-b3c6-41f8-9599-1b969688eb9f','system',NULL,NULL,'job.fenced_rejected','job','c3e8650c-22e9-41b5-a97e-dee5e4af8368',NULL,NULL,NULL,NULL,NULL,'null','null',NULL,'stale lease rejected during succeed',NULL,NULL,'rejected','stale_fencing_token','bf52915c-3455-44bb-9875-34f531281cb7',NULL,'c3e8650c-22e9-41b5-a97e-dee5e4af8368',NULL,NULL,'2026-08-28 09:02:47.729631'),('a9d20fe1-db29-4e50-aa23-7e94f8b62e8d','system',NULL,NULL,'job.cancelled','job','8d723d99-797d-4084-854a-3a671b896635',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"queued\"}','{\"status\": \"cancelled\"}',NULL,'synthetic backpressure cleanup',NULL,NULL,'cancelled',NULL,'68e8831c-12ec-423b-8b92-91f9c46c7d77',NULL,'8d723d99-797d-4084-854a-3a671b896635',NULL,NULL,'2026-08-28 08:53:14.790686'),('aada79a9-a1d7-48b1-9c09-e05f0817bfaa','system',NULL,NULL,'job.enqueued','job','ad4debac-1ef3-40dc-b45e-a58f4797b363','e2-live','e2-live-1787907760',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"30d268b0236cff446ae4b96b861bd81d01a402550c20501ce303d6d02d0d4611\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'3a779de4-dcb9-4bb0-9452-ee80d5f299a9',NULL,'ad4debac-1ef3-40dc-b45e-a58f4797b363',NULL,NULL,'2026-08-28 09:02:41.544657'),('ab372710-b57e-49e2-9e43-0ad09940fabb','system',NULL,NULL,'job.succeeded','job','453a662e-c61c-45ed-843f-1677589f79c4',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2, \"result_digest\": \"1151cf278b48f832b63f0003d17a4eed201965b761184b579b63e9508a1e72bb\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'568738ea-af5f-49d2-b2f3-f9edd845fc92',NULL,'453a662e-c61c-45ed-843f-1677589f79c4',NULL,NULL,'2026-08-28 09:13:02.780559'),('ad141068-d51a-4dd4-adab-ed8a54163520','system',NULL,NULL,'job.fenced_rejected','job','dc02f5cc-8f3b-4217-b006-a4cae7699566',NULL,NULL,NULL,NULL,NULL,'null','null',NULL,'stale lease rejected during succeed',NULL,NULL,'rejected','stale_fencing_token','6eac776b-43da-45b3-bae7-8220b73eabaf',NULL,'dc02f5cc-8f3b-4217-b006-a4cae7699566',NULL,NULL,'2026-08-28 09:06:32.813538'),('adec5a2b-6d2f-4a51-81e7-4c086a02ddde','system',NULL,NULL,'job.succeeded','job','ad4debac-1ef3-40dc-b45e-a58f4797b363',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1, \"result_digest\": \"b56e9f9de5f727d0b414a28792cb584f5b788ef31eb74c7fed148ef5a23fff7a\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'3a779de4-dcb9-4bb0-9452-ee80d5f299a9',NULL,'ad4debac-1ef3-40dc-b45e-a58f4797b363',NULL,NULL,'2026-08-28 09:02:41.605216'),('ae4aeb5b-8088-4f8e-a24d-2c91e950f3b0','system',NULL,NULL,'job.started','job','e250124f-ce80-4060-b4f8-4ed7bfebc64c',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'2fdd0ab9-20a1-48c3-9894-b533bbac5ad2',NULL,'e250124f-ce80-4060-b4f8-4ed7bfebc64c',NULL,NULL,'2026-08-28 08:50:41.320536'),('b051c312-8547-43b3-94fa-28330eb3ce92','system',NULL,NULL,'job.cancelled','job','e250124f-ce80-4060-b4f8-4ed7bfebc64c',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'cancelled','cancel_requested','2fdd0ab9-20a1-48c3-9894-b533bbac5ad2',NULL,'e250124f-ce80-4060-b4f8-4ed7bfebc64c',NULL,NULL,'2026-08-28 08:50:41.338548'),('b207fa14-03ab-4ae4-9e87-87616d5627b1','system',NULL,NULL,'job.started','job','cb0c8ef3-b3ef-465d-937f-9560fa75b30d',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'5c6811b3-3f89-4b75-b87f-747480e73fac',NULL,'cb0c8ef3-b3ef-465d-937f-9560fa75b30d',NULL,NULL,'2026-08-28 09:14:44.189404'),('b2def889-c490-4649-8b28-38b78c88e6f5','system',NULL,NULL,'job.claimed','job','8fa937ba-8f77-47cd-9cd6-129ffff460dc',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'4867c5a6-adc2-4752-891d-c031b8f3d6b9',NULL,'8fa937ba-8f77-47cd-9cd6-129ffff460dc',NULL,NULL,'2026-08-28 09:06:27.325423'),('b35353bd-80d1-4697-926d-0fccfd9cdddc','system',NULL,NULL,'job.claimed','job','3b05aadf-8c73-45f5-a5c4-58a6e9f49869',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'d1a64cef-bcf8-4d8b-b171-31d7a6c107be',NULL,'3b05aadf-8c73-45f5-a5c4-58a6e9f49869',NULL,NULL,'2026-08-28 08:50:01.811132'),('b452a1ff-ef9a-47d3-aa6f-77526c74a8f1','system',NULL,NULL,'job.started','job','e8536c74-76ab-4356-bb60-7075a7692e22',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'990d1c8e-3278-4275-87d0-57228c1e8c63',NULL,'e8536c74-76ab-4356-bb60-7075a7692e22',NULL,NULL,'2026-08-28 09:02:41.814162'),('b4a922c5-752e-4a81-b639-2a6766a1f88b','system',NULL,NULL,'job.lease_expired','job','6dbbe917-0a7b-414c-8093-85be64438425',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"running\", \"fencing_token\": 1}','{\"status\": \"retry_wait\"}',NULL,'lease expired and SQL state was recovered',NULL,NULL,'retry_wait','lease_expired','2ab25bb0-cb69-469b-84ac-12fc3f014e6b',NULL,'6dbbe917-0a7b-414c-8093-85be64438425',NULL,NULL,'2026-08-28 08:59:41.330530'),('b4b85562-a597-47e5-8039-8a2d2d600051','system',NULL,NULL,'job.started','job','6dbbe917-0a7b-414c-8093-85be64438425',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2}',NULL,'leased handler started',NULL,NULL,'running',NULL,'2ab25bb0-cb69-469b-84ac-12fc3f014e6b',NULL,'6dbbe917-0a7b-414c-8093-85be64438425',NULL,NULL,'2026-08-28 09:00:32.980164'),('b7d0413a-36ee-4bd5-9354-1dfc16dbf7dd','system',NULL,NULL,'job.enqueued','job','e250124f-ce80-4060-b4f8-4ed7bfebc64c','e2-live','e2-live-1787907041',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"34e07b5a8b614f9f38103a34c9d1ab89b5dc0d4e109face7c5008f940144c3ff\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'2fdd0ab9-20a1-48c3-9894-b533bbac5ad2',NULL,'e250124f-ce80-4060-b4f8-4ed7bfebc64c',NULL,NULL,'2026-08-28 08:50:40.419203'),('b9c92cfe-7026-4c4a-af6d-9e243bb4697f','system',NULL,NULL,'job.claimed','job','c3e8650c-22e9-41b5-a97e-dee5e4af8368',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 2, \"fencing_token\": 2}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'bf52915c-3455-44bb-9875-34f531281cb7',NULL,'c3e8650c-22e9-41b5-a97e-dee5e4af8368',NULL,NULL,'2026-08-28 09:02:47.722057'),('bad88b3f-1685-4bf6-9e0c-4679a0171bae','system',NULL,NULL,'job.claimed','job','b05c9ec6-98bb-45d8-ba5f-d0831c19f541',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 2, \"fencing_token\": 2}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'ef27f62b-ae9c-45d1-8c25-37bd454109a6',NULL,'b05c9ec6-98bb-45d8-ba5f-d0831c19f541',NULL,NULL,'2026-08-28 09:14:49.828138'),('bc24421b-6a12-494c-9821-ea7175b93cb9','system',NULL,NULL,'job.started','job','8fa937ba-8f77-47cd-9cd6-129ffff460dc',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'4867c5a6-adc2-4752-891d-c031b8f3d6b9',NULL,'8fa937ba-8f77-47cd-9cd6-129ffff460dc',NULL,NULL,'2026-08-28 09:06:27.335544'),('bfe1aecb-c4db-4d76-bcf5-985284f7c693','system',NULL,NULL,'job.cancelled','job','4806906c-559b-49aa-b418-2834f5d19559',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'cancelled','cancel_requested','9329167e-929a-4dab-9974-b8894fdfb097',NULL,'4806906c-559b-49aa-b418-2834f5d19559',NULL,NULL,'2026-08-28 08:53:09.385914'),('c042a5e9-cb9d-482a-b4b4-b33a0cd1b043','system',NULL,NULL,'job.claimed','job','cb0c8ef3-b3ef-465d-937f-9560fa75b30d',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'5c6811b3-3f89-4b75-b87f-747480e73fac',NULL,'cb0c8ef3-b3ef-465d-937f-9560fa75b30d',NULL,NULL,'2026-08-28 09:14:44.180488'),('c19c619e-610e-4f5f-8b19-73620501be46','system',NULL,NULL,'job.cancelled','job','f05e5c5b-e702-4a7c-8e5b-8849e018a805',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'cancelled','cancel_requested','e554f8cb-b6e4-47e4-9e52-6895b01c13f4',NULL,'f05e5c5b-e702-4a7c-8e5b-8849e018a805',NULL,NULL,'2026-08-28 09:14:44.423273'),('c33f2071-68e4-4fe9-9376-a79e896dc080','system',NULL,NULL,'job.started','job','4806906c-559b-49aa-b418-2834f5d19559',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'9329167e-929a-4dab-9974-b8894fdfb097',NULL,'4806906c-559b-49aa-b418-2834f5d19559',NULL,NULL,'2026-08-28 08:53:09.367376'),('c3bfc343-af5e-4e35-81c2-e0424d9ec892','system',NULL,NULL,'job.claimed','job','71bec3d9-fd1b-42c7-b568-1d4cd89a7187',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 2, \"fencing_token\": 2}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'5a5b0403-0ebb-4779-a4b4-2a52ad088633',NULL,'71bec3d9-fd1b-42c7-b568-1d4cd89a7187',NULL,NULL,'2026-08-28 08:53:14.147476'),('c4d66827-cce1-433f-9c8a-d13526c0db6d','system',NULL,NULL,'job.enqueued','job','dc02f5cc-8f3b-4217-b006-a4cae7699566','e2-live','e2-live-1787907986',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"4f30e231ae41e716923ef480d9bf7309a628bb0795bfa34265737ef6beec8941\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'6eac776b-43da-45b3-bae7-8220b73eabaf',NULL,'dc02f5cc-8f3b-4217-b006-a4cae7699566',NULL,NULL,'2026-08-28 09:06:32.782342'),('c87c4e16-15c5-4e2a-bfe3-8b18f4bf0e23','system',NULL,NULL,'job.claimed','job','d8934d75-9a75-40e5-b24f-6bc7337cb3d4',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'f1a78fda-2d8c-40c4-ba70-bb0dd23fe20b',NULL,'d8934d75-9a75-40e5-b24f-6bc7337cb3d4',NULL,NULL,'2026-08-28 08:53:08.926876'),('c96ba1f2-83a6-4b7f-9a95-5889402aa41a','system',NULL,NULL,'job.enqueued','job','4806906c-559b-49aa-b418-2834f5d19559','e2-live','e2-live-1787907188',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"34e07b5a8b614f9f38103a34c9d1ab89b5dc0d4e109face7c5008f940144c3ff\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'9329167e-929a-4dab-9974-b8894fdfb097',NULL,'4806906c-559b-49aa-b418-2834f5d19559',NULL,NULL,'2026-08-28 08:53:08.471619'),('cdd68f18-4eaa-4d02-a1fb-4ca7b0b28e3e','system',NULL,NULL,'job.started','job','52aaa47f-33a3-4fd8-8132-1ff031232e70',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'82de4ba5-6024-4733-99a3-7d3b270bc537',NULL,'52aaa47f-33a3-4fd8-8132-1ff031232e70',NULL,NULL,'2026-08-28 08:50:01.401578'),('ce787011-5e2c-403f-9752-1b3674f6e1b4','system',NULL,NULL,'job.enqueued','job','3ee6574e-1e12-43f3-9d95-164f4bf33f10','e2-live','e2-live-1787907041',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"8fbed32134bbef3538079dd3f443629eb3708208025344d24b6501b64edeec59\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'4a43d51b-0c01-43a9-9f75-b048089a5de5',NULL,'3ee6574e-1e12-43f3-9d95-164f4bf33f10',NULL,NULL,'2026-08-28 08:50:40.411076'),('cfdbc83f-83b9-42d9-8c26-45b255360e3a','system',NULL,NULL,'job.enqueued','job','cb52ec86-33a8-4740-b5be-ada42af7d936','e2-live','e2-live-1787908484-restart',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"686a022a7f742e639e23453dd0ff416b67d70c3b1f24a9e1357076866c3068bb\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'20cf0f20-8335-45e4-a90c-2806aea620bd',NULL,'cb52ec86-33a8-4740-b5be-ada42af7d936',NULL,NULL,'2026-08-28 09:14:49.935068'),('d2021e15-9865-4ef7-ac79-0f16d2f64862','system',NULL,NULL,'job.started','job','4f8a8ecc-a8a0-49f0-9b78-ea8980ef929f',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'ea1a97e9-9d0d-4eff-9317-186e91ca1cbb',NULL,'4f8a8ecc-a8a0-49f0-9b78-ea8980ef929f',NULL,NULL,'2026-08-28 09:14:43.751264'),('d477b24c-671d-4ae4-b947-b497917eff08','system',NULL,NULL,'job.fenced_rejected','job','6acbc215-969e-40f4-a246-e24c2b5fa6bb',NULL,NULL,NULL,NULL,NULL,'null','null',NULL,'stale lease rejected during succeed',NULL,NULL,'rejected','stale_fencing_token','000f885d-6dae-4e91-bbe0-a225f1aa42d6',NULL,'6acbc215-969e-40f4-a246-e24c2b5fa6bb',NULL,NULL,'2026-08-28 08:53:14.770151'),('d4a18f49-c1bd-47cf-902c-aa9eeaf75269','system',NULL,NULL,'job.cancelled','job','2ba78a8c-6e99-45f1-b645-c0dc18bd455c',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"queued\"}','{\"status\": \"cancelled\"}',NULL,'synthetic backpressure cleanup',NULL,NULL,'cancelled',NULL,'6c1e0052-5f90-416f-bcb6-a89b9b147968',NULL,'2ba78a8c-6e99-45f1-b645-c0dc18bd455c',NULL,NULL,'2026-08-28 09:14:49.864012'),('d53da767-6601-47ef-8e05-0b718e7a98c6','system',NULL,NULL,'job.enqueued','job','f05e5c5b-e702-4a7c-8e5b-8849e018a805','e2-live','e2-live-1787908484',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"34e07b5a8b614f9f38103a34c9d1ab89b5dc0d4e109face7c5008f940144c3ff\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'e554f8cb-b6e4-47e4-9e52-6895b01c13f4',NULL,'f05e5c5b-e702-4a7c-8e5b-8849e018a805',NULL,NULL,'2026-08-28 09:14:43.730212'),('d66f36fd-f97c-4f05-a0b4-90fbfa400e8e','system',NULL,NULL,'job.enqueued','job','40469f02-80d4-4d5f-8c3b-ae0ac6a31cda','e2-live','e2-live-1787907001',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"8fbed32134bbef3538079dd3f443629eb3708208025344d24b6501b64edeec59\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'bbda1cee-17ec-4b71-96aa-714633a8f64b',NULL,'40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',NULL,NULL,'2026-08-28 08:50:01.149269'),('d6ee8b68-fc73-4e0e-922c-29efd180a9b3','system',NULL,NULL,'job.started','job','3b05aadf-8c73-45f5-a5c4-58a6e9f49869',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'d1a64cef-bcf8-4d8b-b171-31d7a6c107be',NULL,'3b05aadf-8c73-45f5-a5c4-58a6e9f49869',NULL,NULL,'2026-08-28 08:50:01.819211'),('d91014ee-41af-4974-b8bf-451a553734b8','system',NULL,NULL,'job.started','job','5a220335-bdeb-4201-89a8-43b64de84159',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'ffb19ea3-e520-41f2-82b4-3d8cba768ae7',NULL,'5a220335-bdeb-4201-89a8-43b64de84159',NULL,NULL,'2026-08-28 09:06:27.562544'),('da0b89d8-93ac-45cc-8d6b-8e00054568d3','system',NULL,NULL,'job.started','job','bdac56dc-a822-4da7-b44d-bc9a0c9a32e8',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'ae5e4fe9-fd6c-4f55-a3d5-c013b758b16f',NULL,'bdac56dc-a822-4da7-b44d-bc9a0c9a32e8',NULL,NULL,'2026-08-28 09:02:42.263102'),('de5ff536-a83c-4947-84ab-1b36724a9cd0','system',NULL,NULL,'job.enqueued','job','b20b2caa-4963-4001-9498-940e2ed50536','e2-live','e2-live-1787907041',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"30d268b0236cff446ae4b96b861bd81d01a402550c20501ce303d6d02d0d4611\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'9af42a37-9d9f-45e3-813c-33b3d0a78e11',NULL,'b20b2caa-4963-4001-9498-940e2ed50536',NULL,NULL,'2026-08-28 08:50:40.390045'),('e0160afe-b4e1-4c8f-aa12-2b50267da795','system',NULL,NULL,'job.retry_wait','job','71bec3d9-fd1b-42c7-b568-1d4cd89a7187',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'retry_wait','synthetic_retry','5a5b0403-0ebb-4779-a4b4-2a52ad088633',NULL,'71bec3d9-fd1b-42c7-b568-1d4cd89a7187',NULL,NULL,'2026-08-28 08:53:09.160033'),('e09fb9ab-9abb-4efe-b1d6-101f83a70f31','system',NULL,NULL,'job.claimed','job','3ee6574e-1e12-43f3-9d95-164f4bf33f10',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 2, \"fencing_token\": 2}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'4a43d51b-0c01-43a9-9f75-b048089a5de5',NULL,'3ee6574e-1e12-43f3-9d95-164f4bf33f10',NULL,NULL,'2026-08-28 08:50:46.117981'),('e6730b5d-b479-48ee-b486-96b21a6afb06','system',NULL,NULL,'job.succeeded','job','b05c9ec6-98bb-45d8-ba5f-d0831c19f541',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2, \"result_digest\": \"a4034c0dd4380bf6a870e4d8315ebc314576a40778f7c89c0e7d3a0f0f54fc76\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'ef27f62b-ae9c-45d1-8c25-37bd454109a6',NULL,'b05c9ec6-98bb-45d8-ba5f-d0831c19f541',NULL,NULL,'2026-08-28 09:14:49.845747'),('e772d367-def5-4401-85c0-417517b9234f','system',NULL,NULL,'job.claimed','job','434cfb34-fcc8-4c21-afa3-b426d715bbb6',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'5e508fa9-f644-41ba-bce2-3ff477a31ed7',NULL,'434cfb34-fcc8-4c21-afa3-b426d715bbb6',NULL,NULL,'2026-08-28 08:53:08.482953'),('ec188d15-66e4-4811-9425-ef8d3c54544e','system',NULL,NULL,'job.enqueued','job','8fa937ba-8f77-47cd-9cd6-129ffff460dc','e2-live','e2-live-1787907986',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"30d268b0236cff446ae4b96b861bd81d01a402550c20501ce303d6d02d0d4611\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'4867c5a6-adc2-4752-891d-c031b8f3d6b9',NULL,'8fa937ba-8f77-47cd-9cd6-129ffff460dc',NULL,NULL,'2026-08-28 09:06:27.286706'),('ec8ec2f7-b612-41d7-b98a-78af939739fc','system',NULL,NULL,'job.claimed','job','07e5fc05-e305-4281-9ae6-ec9cd26e576e',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'dada6dc4-4c38-45a4-abce-9e0d593fb250',NULL,'07e5fc05-e305-4281-9ae6-ec9cd26e576e',NULL,NULL,'2026-08-28 09:02:42.037340'),('ecd870c5-3ea1-4d75-8e4a-91f4c10aeed0','system',NULL,NULL,'job.claimed','job','7fdfb197-f345-4864-a59c-4d2e787f3a4b',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'54d1b008-af26-4a88-b570-dfd4145cc982',NULL,'7fdfb197-f345-4864-a59c-4d2e787f3a4b',NULL,NULL,'2026-08-28 08:50:01.170293'),('f0301c15-d12d-45a5-9855-2c0b76a7019b','system',NULL,NULL,'job.enqueued','job','3eebd495-227e-42fa-bbb6-9d6f0af097cc','e2-live','e2-live-1787907760-restart',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"686a022a7f742e639e23453dd0ff416b67d70c3b1f24a9e1357076866c3068bb\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'4da191b1-a36b-436c-8cd1-f3d445a6e85e',NULL,'3eebd495-227e-42fa-bbb6-9d6f0af097cc',NULL,NULL,'2026-08-28 09:02:47.826258'),('f03468cc-08ec-4950-a470-3ebe6aa80147','system',NULL,NULL,'job.claimed','job','cdf1cc2a-9914-4041-bffa-d1ca7ba8cbe4',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'c53a45e4-e645-458e-937f-d359929b0ec3',NULL,'cdf1cc2a-9914-4041-bffa-d1ca7ba8cbe4',NULL,NULL,'2026-08-28 08:53:08.696848'),('f18c990b-d398-4a51-bee7-a9d864a68863','system',NULL,NULL,'job.started','job','7da7ac7e-ad14-4056-acae-d621701fab8e',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'07125c6e-d8ec-4f66-bdbd-5c31ac00e213',NULL,'7da7ac7e-ad14-4056-acae-d621701fab8e',NULL,NULL,'2026-08-28 08:50:40.902480'),('f1d208e9-29c9-4010-b149-c20c2ac6ce89','system',NULL,NULL,'job.enqueued','job','5ffc8e31-43f5-43d6-9c45-75a34f526ef2','e2-live','e2-live-1787907986',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"34e07b5a8b614f9f38103a34c9d1ab89b5dc0d4e109face7c5008f940144c3ff\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'b83de93f-8297-4b36-be6d-eb8811669569',NULL,'5ffc8e31-43f5-43d6-9c45-75a34f526ef2',NULL,NULL,'2026-08-28 09:06:27.313863'),('f36eb686-e209-4ba0-b5ee-91820bae495f','system',NULL,NULL,'job.enqueued','job','07e5fc05-e305-4281-9ae6-ec9cd26e576e','e2-live','e2-live-1787907760',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"8fbed32134bbef3538079dd3f443629eb3708208025344d24b6501b64edeec59\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'dada6dc4-4c38-45a4-abce-9e0d593fb250',NULL,'07e5fc05-e305-4281-9ae6-ec9cd26e576e',NULL,NULL,'2026-08-28 09:02:41.564907'),('f39db6b3-40b0-4b9a-a3d1-0558ca85fe06','system',NULL,NULL,'job.started','job','3ee6574e-1e12-43f3-9d95-164f4bf33f10',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1}',NULL,'leased handler started',NULL,NULL,'running',NULL,'4a43d51b-0c01-43a9-9f75-b048089a5de5',NULL,'3ee6574e-1e12-43f3-9d95-164f4bf33f10',NULL,NULL,'2026-08-28 08:50:41.102282'),('f453a6fe-55f7-4b34-ac50-35bf4f8c4887','system',NULL,NULL,'job.enqueued','job','d8934d75-9a75-40e5-b24f-6bc7337cb3d4','e2-live','e2-live-1787907188',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"073fd96e2966d29f69cbbf3303aeb53f654eab14bab37acb1c7e04a52b85ddd3\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'f1a78fda-2d8c-40c4-ba70-bb0dd23fe20b',NULL,'d8934d75-9a75-40e5-b24f-6bc7337cb3d4',NULL,NULL,'2026-08-28 08:53:08.455609'),('f46893de-609b-49fb-a020-15e4bf415f5f','system',NULL,NULL,'job.retry_wait','job','cb0c8ef3-b3ef-465d-937f-9560fa75b30d',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'retry_wait','synthetic_retry','5c6811b3-3f89-4b75-b87f-747480e73fac',NULL,'cb0c8ef3-b3ef-465d-937f-9560fa75b30d',NULL,NULL,'2026-08-28 09:14:44.197080'),('f50a665e-a180-462f-8b1f-ce1b0e0bff64','system',NULL,NULL,'job.succeeded','job','3ee6574e-1e12-43f3-9d95-164f4bf33f10',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2, \"result_digest\": \"93105a2e0623d5c1c6d9054effed3165e3f350748c3a7163a620e2f38cb03756\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'4a43d51b-0c01-43a9-9f75-b048089a5de5',NULL,'3ee6574e-1e12-43f3-9d95-164f4bf33f10',NULL,NULL,'2026-08-28 08:50:46.138909'),('f5206b57-75ee-4a7c-9a54-80382cdb9e77','system',NULL,NULL,'job.succeeded','job','7fdfb197-f345-4864-a59c-4d2e787f3a4b',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1, \"result_digest\": \"b56e9f9de5f727d0b414a28792cb584f5b788ef31eb74c7fed148ef5a23fff7a\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'54d1b008-af26-4a88-b570-dfd4145cc982',NULL,'7fdfb197-f345-4864-a59c-4d2e787f3a4b',NULL,NULL,'2026-08-28 08:50:01.188993'),('f61c41a8-ede0-4428-bf29-673e4af0f230','system',NULL,NULL,'job.claimed','job','6dbbe917-0a7b-414c-8093-85be64438425',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 2, \"fencing_token\": 2}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'2ab25bb0-cb69-469b-84ac-12fc3f014e6b',NULL,'6dbbe917-0a7b-414c-8093-85be64438425',NULL,NULL,'2026-08-28 09:00:32.970251'),('f62284d6-c29a-494f-838a-82f7d89ab7de','system',NULL,NULL,'job.succeeded','job','cb0c8ef3-b3ef-465d-937f-9560fa75b30d',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2, \"result_digest\": \"93105a2e0623d5c1c6d9054effed3165e3f350748c3a7163a620e2f38cb03756\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'5c6811b3-3f89-4b75-b87f-747480e73fac',NULL,'cb0c8ef3-b3ef-465d-937f-9560fa75b30d',NULL,NULL,'2026-08-28 09:14:49.204846'),('f70b36f7-ba98-4d68-bc4d-4c2c0a5085ab','system',NULL,NULL,'job.claimed','job','b20b2caa-4963-4001-9498-940e2ed50536',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'9af42a37-9d9f-45e3-813c-33b3d0a78e11',NULL,'b20b2caa-4963-4001-9498-940e2ed50536',NULL,NULL,'2026-08-28 08:50:40.664563'),('f7e58317-e71f-4041-8a44-323e061525af','system',NULL,NULL,'job.dead_letter','job','5a220335-bdeb-4201-89a8-43b64de84159',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'dead_letter','unknown_job_type','ffb19ea3-e520-41f2-82b4-3d8cba768ae7',NULL,'5a220335-bdeb-4201-89a8-43b64de84159',NULL,NULL,'2026-08-28 09:06:27.570990'),('f8b3ac4f-91b9-4842-9829-82dfb302d13a','system',NULL,NULL,'job.succeeded','job','cdf1cc2a-9914-4041-bffa-d1ca7ba8cbe4',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 1, \"result_digest\": \"b56e9f9de5f727d0b414a28792cb584f5b788ef31eb74c7fed148ef5a23fff7a\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'c53a45e4-e645-458e-937f-d359929b0ec3',NULL,'cdf1cc2a-9914-4041-bffa-d1ca7ba8cbe4',NULL,NULL,'2026-08-28 08:53:08.714770'),('fa6c7294-1eeb-406e-9123-5cee5151959a','system',NULL,NULL,'job.fenced_rejected','job','8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',NULL,NULL,NULL,NULL,NULL,'null','null',NULL,'stale lease rejected during succeed',NULL,NULL,'rejected','stale_fencing_token','26224654-9f6b-4861-a1e1-3ca4cbd6f710',NULL,'8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',NULL,NULL,'2026-08-28 08:50:06.835240'),('fb1ff570-3e19-4fe2-8b4d-84ff41db298f','system',NULL,NULL,'job.cancelled','job','37818753-632e-41e4-b680-31e9213beb77',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"queued\"}','{\"status\": \"cancelled\"}',NULL,'synthetic backpressure cleanup',NULL,NULL,'cancelled',NULL,'834484d6-2ec1-47d0-b3cc-a413ba419a29',NULL,'37818753-632e-41e4-b680-31e9213beb77',NULL,NULL,'2026-08-28 09:02:47.753122'),('fb2d27d9-8051-4077-801b-3e6256e3d9ce','system',NULL,NULL,'job.claimed','job','ad4debac-1ef3-40dc-b45e-a58f4797b363',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'3a779de4-dcb9-4bb0-9452-ee80d5f299a9',NULL,'ad4debac-1ef3-40dc-b45e-a58f4797b363',NULL,NULL,'2026-08-28 09:02:41.583719'),('fc626399-aa71-46bd-b1c0-15cb0bc024b5','system',NULL,NULL,'job.claimed','job','08e3e7a5-1557-42bb-a6db-622f7739417e',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'9fb8ce83-571c-47b4-98b3-44d0e9236e0b',NULL,'08e3e7a5-1557-42bb-a6db-622f7739417e',NULL,NULL,'2026-08-28 09:14:43.963530'),('fcb86095-d5d0-4333-884e-c6bd49b62378','system',NULL,NULL,'job.enqueued','job','bdac56dc-a822-4da7-b44d-bc9a0c9a32e8','e2-live','e2-live-1787907760',NULL,NULL,NULL,'null','{\"status\": \"queued\", \"payload_digest\": \"34e07b5a8b614f9f38103a34c9d1ab89b5dc0d4e109face7c5008f940144c3ff\"}',NULL,'durable job accepted',NULL,NULL,'accepted',NULL,'ae5e4fe9-fd6c-4f55-a3d5-c013b758b16f',NULL,'bdac56dc-a822-4da7-b44d-bc9a0c9a32e8',NULL,NULL,'2026-08-28 09:02:41.572971'),('fcbf2f19-741f-4cc1-bafe-527e4c1eae01','system',NULL,NULL,'job.retry_wait','job','40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'handler failure resolved by retry policy',NULL,NULL,'retry_wait','synthetic_retry','bbda1cee-17ec-4b71-96aa-714633a8f64b',NULL,'40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',NULL,NULL,'2026-08-28 08:50:01.611497'),('ff0e6675-0406-47ca-845a-a11f626169f9','system',NULL,NULL,'job.cancelled','job','223f5b9c-0c2d-4c2e-826e-b2f520bc0f4b',NULL,NULL,NULL,NULL,NULL,'{\"status\": \"queued\"}','{\"status\": \"cancelled\"}',NULL,'synthetic backpressure cleanup',NULL,NULL,'cancelled',NULL,'7b9b1a01-58af-499a-864c-a6c21812cffd',NULL,'223f5b9c-0c2d-4c2e-826e-b2f520bc0f4b',NULL,NULL,'2026-08-28 08:50:06.856604'),('ff314cdc-cf3a-48da-9ee8-bf593238b4a7','system',NULL,NULL,'job.claimed','job','bdac56dc-a822-4da7-b44d-bc9a0c9a32e8',NULL,NULL,NULL,NULL,NULL,'null','{\"attempt\": 1, \"fencing_token\": 1}',NULL,'runner acquired SQL lease',NULL,NULL,'leased',NULL,'ae5e4fe9-fd6c-4f55-a3d5-c013b758b16f',NULL,'bdac56dc-a822-4da7-b44d-bc9a0c9a32e8',NULL,NULL,'2026-08-28 09:02:42.253719'),('ffeb3867-4407-48b0-9a7e-71cf3d540c07','system',NULL,NULL,'job.succeeded','job','07e5fc05-e305-4281-9ae6-ec9cd26e576e',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2, \"result_digest\": \"93105a2e0623d5c1c6d9054effed3165e3f350748c3a7163a620e2f38cb03756\"}',NULL,'handler result committed with matching fence',NULL,NULL,'succeeded',NULL,'dada6dc4-4c38-45a4-abce-9e0d593fb250',NULL,'07e5fc05-e305-4281-9ae6-ec9cd26e576e',NULL,NULL,'2026-08-28 09:02:47.101989'),('fffdf17b-aa3f-49b7-aefc-42b1c1b3c7b9','system',NULL,NULL,'job.started','job','3ee6574e-1e12-43f3-9d95-164f4bf33f10',NULL,NULL,NULL,NULL,NULL,'null','{\"fencing_token\": 2}',NULL,'leased handler started',NULL,NULL,'running',NULL,'4a43d51b-0c01-43a9-9f75-b048089a5de5',NULL,'3ee6574e-1e12-43f3-9d95-164f4bf33f10',NULL,NULL,'2026-08-28 08:50:46.126862');
/*!40000 ALTER TABLE `audit_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `auth_sessions`
--

DROP TABLE IF EXISTS `auth_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_sessions` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `user_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `status` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'active',
  `issued_token_version` bigint NOT NULL,
  `revision` bigint NOT NULL DEFAULT '1',
  `expires_at` datetime(6) NOT NULL,
  `revoked_at` datetime(6) DEFAULT NULL,
  `revoke_reason` varchar(4096) DEFAULT NULL,
  `last_seen_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `ix_auth_sessions_user_status` (`user_id`,`status`),
  KEY `ix_auth_sessions_expires` (`status`,`expires_at`),
  CONSTRAINT `auth_sessions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_auth_sessions_id_uuid` CHECK (regexp_like(`id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_auth_sessions_status` CHECK ((`status` in (_ascii'active',_ascii'revoked',_ascii'expired')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auth_sessions`
--

LOCK TABLES `auth_sessions` WRITE;
/*!40000 ALTER TABLE `auth_sessions` DISABLE KEYS */;
/*!40000 ALTER TABLE `auth_sessions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `chat_messages`
--

DROP TABLE IF EXISTS `chat_messages`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chat_messages` (
  `id` int NOT NULL AUTO_INCREMENT,
  `session_id` varchar(64) DEFAULT NULL,
  `role` varchar(32) NOT NULL,
  `content` text NOT NULL,
  `metadata` json DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `session_id` (`session_id`),
  KEY `ix_chat_messages_id` (`id`),
  CONSTRAINT `chat_messages_ibfk_1` FOREIGN KEY (`session_id`) REFERENCES `chat_sessions` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `chat_messages`
--

LOCK TABLES `chat_messages` WRITE;
/*!40000 ALTER TABLE `chat_messages` DISABLE KEYS */;
/*!40000 ALTER TABLE `chat_messages` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `chat_sessions`
--

DROP TABLE IF EXISTS `chat_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chat_sessions` (
  `id` varchar(64) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `title` varchar(255) DEFAULT NULL,
  `metadata` json DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_chat_sessions_id` (`id`),
  KEY `ix_chat_sessions_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `chat_sessions`
--

LOCK TABLES `chat_sessions` WRITE;
/*!40000 ALTER TABLE `chat_sessions` DISABLE KEYS */;
/*!40000 ALTER TABLE `chat_sessions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `job_attempts`
--

DROP TABLE IF EXISTS `job_attempts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `job_attempts` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `job_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `attempt_number` int NOT NULL,
  `lease_owner` varchar(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `fencing_token` bigint NOT NULL,
  `started_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `heartbeat_at` datetime(6) DEFAULT NULL,
  `finished_at` datetime(6) DEFAULT NULL,
  `outcome` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'leased',
  `error_code` varchar(64) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `error_detail` text,
  `worker_metadata_json` json NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_job_attempts_job_number` (`job_id`,`attempt_number`),
  KEY `ix_job_attempts_job_started` (`job_id`,`started_at`),
  KEY `ix_job_attempts_lease` (`lease_owner`,`fencing_token`),
  CONSTRAINT `job_attempts_ibfk_1` FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`) ON DELETE CASCADE,
  CONSTRAINT `ck_job_attempts_fencing` CHECK ((`fencing_token` > 0)),
  CONSTRAINT `ck_job_attempts_id_uuid` CHECK (regexp_like(`id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_job_attempts_number` CHECK ((`attempt_number` > 0)),
  CONSTRAINT `ck_job_attempts_outcome` CHECK ((`outcome` in (_ascii'leased',_ascii'running',_ascii'succeeded',_ascii'retry_wait',_ascii'cancelled',_ascii'dead_letter',_ascii'abandoned',_ascii'fenced')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `job_attempts`
--

LOCK TABLES `job_attempts` WRITE;
/*!40000 ALTER TABLE `job_attempts` DISABLE KEYS */;
INSERT INTO `job_attempts` VALUES ('00dd2ede-9f82-49b3-a53b-50045a0e7a31','8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',1,'e2-fence-a',1,'2026-08-28 08:50:07.575919','2026-08-28 08:50:07.575919','2026-08-28 08:50:09.575919','abandoned','lease_expired',NULL,'{\"schema_version\": 1}'),('06579d2d-4913-45d5-a307-3725133f5e25','40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',2,'runner-490f4a1c-e953-40ca-8685-6ddf9b4b5cc2',2,'2026-08-28 08:50:06.000000','2026-08-28 08:50:06.000000','2026-08-28 08:50:06.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('081affc2-a29f-45c0-ab9e-c722499c314b','453a662e-c61c-45ed-843f-1677589f79c4',1,'runner-a574be0f-9f20-40d3-87d2-36bbb6e5fcc0',1,'2026-08-28 09:06:33.000000','2026-08-28 09:06:33.000000','2026-08-28 09:12:22.213085','abandoned','lease_expired',NULL,'{\"schema_version\": 1}'),('0bd396c5-239e-4a8f-92e5-8dac73ba1790','a8e99039-8b40-4a9e-9853-968f9c0f6b15',2,'runner-b425b0cc-a0d3-45fb-9894-f53ea707bf42',2,'2026-08-28 09:06:32.000000','2026-08-28 09:06:32.000000','2026-08-28 09:06:32.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('154b667f-058c-4337-8adb-f33f82aba90a','6acbc215-969e-40f4-a246-e24c2b5fa6bb',2,'e2-fence-b',2,'2026-08-28 08:53:23.114197','2026-08-28 08:53:23.114197','2026-08-28 08:53:24.114197','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('21312cee-05e2-4796-860f-b6b75fd76287','71bec3d9-fd1b-42c7-b568-1d4cd89a7187',1,'runner-6c4d5774-622a-40b6-b09e-0e312b4bdf77',1,'2026-08-28 08:53:09.000000','2026-08-28 08:53:09.000000','2026-08-28 08:53:09.000000','retry_wait','synthetic_retry','first attempt intentionally failed','{\"schema_version\": 1}'),('246555bc-ad42-4689-849c-fc93b3bfc9fb','7fdfb197-f345-4864-a59c-4d2e787f3a4b',1,'runner-490f4a1c-e953-40ca-8685-6ddf9b4b5cc2',1,'2026-08-28 08:50:01.000000','2026-08-28 08:50:01.000000','2026-08-28 08:50:01.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('24e831a4-8e87-4b24-8e50-a057605fc568','3ee6574e-1e12-43f3-9d95-164f4bf33f10',1,'runner-f35f3f83-c0ee-4ee5-9b9b-cb81a28e08a0',1,'2026-08-28 08:50:41.000000','2026-08-28 08:50:41.000000','2026-08-28 08:50:41.000000','retry_wait','synthetic_retry','first attempt intentionally failed','{\"schema_version\": 1}'),('271ed074-cda5-47b3-9b7a-b98ff288416c','b20b2caa-4963-4001-9498-940e2ed50536',1,'runner-f35f3f83-c0ee-4ee5-9b9b-cb81a28e08a0',1,'2026-08-28 08:50:40.000000','2026-08-28 08:50:40.000000','2026-08-28 08:50:40.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('2cae30ea-61b6-46a0-a08b-aec087e5d8d5','4f8a8ecc-a8a0-49f0-9b78-ea8980ef929f',1,'runner-dfba26b1-17ef-4e32-ae4c-7a46590eb829',1,'2026-08-28 09:14:43.000000','2026-08-28 09:14:43.000000','2026-08-28 09:14:43.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('35b6c913-2028-4eba-8210-66fbe8827843','6acbc215-969e-40f4-a246-e24c2b5fa6bb',1,'e2-fence-a',1,'2026-08-28 08:53:15.114197','2026-08-28 08:53:15.114197','2026-08-28 08:53:17.114197','abandoned','lease_expired',NULL,'{\"schema_version\": 1}'),('37209e67-cb16-41ce-91c6-d00980adc586','a8e99039-8b40-4a9e-9853-968f9c0f6b15',1,'runner-b425b0cc-a0d3-45fb-9894-f53ea707bf42',1,'2026-08-28 09:06:27.000000','2026-08-28 09:06:27.000000','2026-08-28 09:06:27.000000','retry_wait','synthetic_retry','first attempt intentionally failed','{\"schema_version\": 1}'),('38448398-79fd-461f-aa52-ccd41b7a67c3','c3e8650c-22e9-41b5-a97e-dee5e4af8368',1,'e2-fence-a',1,'2026-08-28 09:02:47.636198','2026-08-28 09:02:47.636198','2026-08-28 09:02:49.636198','abandoned','lease_expired',NULL,'{\"schema_version\": 1}'),('38a84ded-124e-4758-a24f-b6ead26c1055','e250124f-ce80-4060-b4f8-4ed7bfebc64c',1,'runner-f35f3f83-c0ee-4ee5-9b9b-cb81a28e08a0',1,'2026-08-28 08:50:41.000000','2026-08-28 08:50:41.000000','2026-08-28 08:50:41.000000','cancelled','cancel_requested','job cancellation was requested before the handler completed','{\"schema_version\": 1}'),('39c89ac8-c784-4740-9a4f-eef386e9ccfe','cb0c8ef3-b3ef-465d-937f-9560fa75b30d',2,'runner-dfba26b1-17ef-4e32-ae4c-7a46590eb829',2,'2026-08-28 09:14:49.000000','2026-08-28 09:14:49.000000','2026-08-28 09:14:49.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('3b7640a5-b6b0-4039-8f1f-0bee73a58b78','08e3e7a5-1557-42bb-a6db-622f7739417e',1,'runner-dfba26b1-17ef-4e32-ae4c-7a46590eb829',1,'2026-08-28 09:14:43.000000','2026-08-28 09:14:43.000000','2026-08-28 09:14:43.000000','dead_letter','unknown_job_type','no handler registered for e2.live.unknown','{\"schema_version\": 1}'),('3c42ddb4-ca65-4290-b57c-0a4678c0a70f','52aaa47f-33a3-4fd8-8132-1ff031232e70',1,'runner-490f4a1c-e953-40ca-8685-6ddf9b4b5cc2',1,'2026-08-28 08:50:01.000000','2026-08-28 08:50:01.000000','2026-08-28 08:50:01.000000','dead_letter','unknown_job_type','no handler registered for e2.live.unknown','{\"schema_version\": 1}'),('479d1887-0a33-4c1b-a452-a09657cc7fbc','3ee6574e-1e12-43f3-9d95-164f4bf33f10',2,'runner-f35f3f83-c0ee-4ee5-9b9b-cb81a28e08a0',2,'2026-08-28 08:50:46.000000','2026-08-28 08:50:46.000000','2026-08-28 08:50:46.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('497c6ef9-515f-4029-9632-02d1cb780e38','3b05aadf-8c73-45f5-a5c4-58a6e9f49869',1,'runner-490f4a1c-e953-40ca-8685-6ddf9b4b5cc2',1,'2026-08-28 08:50:01.000000','2026-08-28 08:50:01.000000','2026-08-28 08:50:01.000000','cancelled','cancel_requested','job cancellation was requested before the handler completed','{\"schema_version\": 1}'),('52ba867b-9d39-4685-8300-9567028c5ba7','5a220335-bdeb-4201-89a8-43b64de84159',1,'runner-b425b0cc-a0d3-45fb-9894-f53ea707bf42',1,'2026-08-28 09:06:27.000000','2026-08-28 09:06:27.000000','2026-08-28 09:06:27.000000','dead_letter','unknown_job_type','no handler registered for e2.live.unknown','{\"schema_version\": 1}'),('5393169e-1633-43b4-883b-3faec868c9f9','453a662e-c61c-45ed-843f-1677589f79c4',2,'runner-31f31537-bb34-4342-a968-179c0968e1a3',2,'2026-08-28 09:13:02.000000','2026-08-28 09:13:02.000000','2026-08-28 09:13:02.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('5cffd24e-7213-46cd-8761-4b74dcbfeea5','07e5fc05-e305-4281-9ae6-ec9cd26e576e',1,'runner-4a9b0823-97e7-4fb5-838d-c2d09560e2ed',1,'2026-08-28 09:02:42.000000','2026-08-28 09:02:42.000000','2026-08-28 09:02:42.000000','retry_wait','synthetic_retry','first attempt intentionally failed','{\"schema_version\": 1}'),('5ef660f3-9856-4705-98da-3dcd73ce0309','ad4debac-1ef3-40dc-b45e-a58f4797b363',1,'runner-4a9b0823-97e7-4fb5-838d-c2d09560e2ed',1,'2026-08-28 09:02:41.000000','2026-08-28 09:02:41.000000','2026-08-28 09:02:41.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('6dd31fc3-b38e-49bb-a101-8b951a461923','f05e5c5b-e702-4a7c-8e5b-8849e018a805',1,'runner-dfba26b1-17ef-4e32-ae4c-7a46590eb829',1,'2026-08-28 09:14:44.000000','2026-08-28 09:14:44.000000','2026-08-28 09:14:44.000000','cancelled','cancel_requested','job cancellation was requested before the handler completed','{\"schema_version\": 1}'),('7526ed7d-9a57-49a6-b17f-e6d2a52b6483','e8536c74-76ab-4356-bb60-7075a7692e22',1,'runner-4a9b0823-97e7-4fb5-838d-c2d09560e2ed',1,'2026-08-28 09:02:41.000000','2026-08-28 09:02:41.000000','2026-08-28 09:02:41.000000','dead_letter','unknown_job_type','no handler registered for e2.live.unknown','{\"schema_version\": 1}'),('790a8ff3-b64e-4534-b71f-dac620812984','dc02f5cc-8f3b-4217-b006-a4cae7699566',1,'e2-fence-a',1,'2026-08-28 09:06:32.665836','2026-08-28 09:06:32.665836','2026-08-28 09:06:34.665836','abandoned','lease_expired',NULL,'{\"schema_version\": 1}'),('7caf262a-99a9-4c94-ae92-6ff5ed3ccd83','8bc7774a-bb4b-4b70-87fa-1c50e1d9e803',2,'e2-fence-b',2,'2026-08-28 08:50:15.575919','2026-08-28 08:50:15.575919','2026-08-28 08:50:16.575919','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('7fd86df1-7be8-4488-b0d3-e4066119cae2','b05c9ec6-98bb-45d8-ba5f-d0831c19f541',1,'e2-fence-a',1,'2026-08-28 09:14:50.791816','2026-08-28 09:14:50.791816','2026-08-28 09:14:52.791816','abandoned','lease_expired',NULL,'{\"schema_version\": 1}'),('872b4cb6-b3e8-4a62-ab8c-494657a29b75','07e5fc05-e305-4281-9ae6-ec9cd26e576e',2,'runner-4a9b0823-97e7-4fb5-838d-c2d09560e2ed',2,'2026-08-28 09:02:47.000000','2026-08-28 09:02:47.000000','2026-08-28 09:02:47.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('8733a62f-1980-456d-9de3-938678e88f81','c3e8650c-22e9-41b5-a97e-dee5e4af8368',2,'e2-fence-b',2,'2026-08-28 09:02:55.636198','2026-08-28 09:02:55.636198','2026-08-28 09:02:56.636198','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('8f82bbe1-e23e-48eb-9bc6-5f64510250f4','6dbbe917-0a7b-414c-8093-85be64438425',1,'runner-8bc756eb-1b7b-4ad0-a55f-5ebe83a13f93',1,'2026-08-28 08:53:15.000000','2026-08-28 08:53:15.000000','2026-08-28 08:59:41.000000','abandoned','lease_expired',NULL,'{\"schema_version\": 1}'),('ab01608b-c56e-4632-a5ab-439cd81bd0c2','cdf1cc2a-9914-4041-bffa-d1ca7ba8cbe4',1,'runner-6c4d5774-622a-40b6-b09e-0e312b4bdf77',1,'2026-08-28 08:53:08.000000','2026-08-28 08:53:08.000000','2026-08-28 08:53:08.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('af4ee969-c53f-4203-ab8a-f04c73584939','b05c9ec6-98bb-45d8-ba5f-d0831c19f541',2,'e2-fence-b',2,'2026-08-28 09:14:58.791816','2026-08-28 09:14:58.791816','2026-08-28 09:14:59.791816','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('b688176c-7522-475b-be06-3d8d6db79ce8','5ffc8e31-43f5-43d6-9c45-75a34f526ef2',1,'runner-b425b0cc-a0d3-45fb-9894-f53ea707bf42',1,'2026-08-28 09:06:27.000000','2026-08-28 09:06:27.000000','2026-08-28 09:06:27.000000','cancelled','cancel_requested','job cancellation was requested before the handler completed','{\"schema_version\": 1}'),('b7aaafef-3d18-4390-8ba5-471dd4411c4c','4806906c-559b-49aa-b418-2834f5d19559',1,'runner-6c4d5774-622a-40b6-b09e-0e312b4bdf77',1,'2026-08-28 08:53:09.000000','2026-08-28 08:53:09.000000','2026-08-28 08:53:09.000000','cancelled','cancel_requested','job cancellation was requested before the handler completed','{\"schema_version\": 1}'),('bd1d0da2-7709-43fc-a702-288c1ca86e0d','cb52ec86-33a8-4740-b5be-ada42af7d936',1,'runner-25fdfc42-c6b4-41e2-bd07-41045c21f2b4',1,'2026-08-28 09:14:50.000000','2026-08-28 09:14:50.000000','2026-08-28 09:26:11.000000','abandoned','lease_expired',NULL,'{\"schema_version\": 1}'),('bee76360-1c50-4ba0-94b1-4c57d3bad100','71bec3d9-fd1b-42c7-b568-1d4cd89a7187',2,'runner-6c4d5774-622a-40b6-b09e-0e312b4bdf77',2,'2026-08-28 08:53:14.000000','2026-08-28 08:53:14.000000','2026-08-28 08:53:14.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('c1bdb74f-1e0f-4f39-91ee-ea4971db3a2b','40469f02-80d4-4d5f-8c3b-ae0ac6a31cda',1,'runner-490f4a1c-e953-40ca-8685-6ddf9b4b5cc2',1,'2026-08-28 08:50:01.000000','2026-08-28 08:50:01.000000','2026-08-28 08:50:01.000000','retry_wait','synthetic_retry','first attempt intentionally failed','{\"schema_version\": 1}'),('ce4d8ba2-8d82-4d1d-8e9b-ca6c1abdd5bb','cb0c8ef3-b3ef-465d-937f-9560fa75b30d',1,'runner-dfba26b1-17ef-4e32-ae4c-7a46590eb829',1,'2026-08-28 09:14:44.000000','2026-08-28 09:14:44.000000','2026-08-28 09:14:44.000000','retry_wait','synthetic_retry','first attempt intentionally failed','{\"schema_version\": 1}'),('d3817922-b7c7-472d-929e-e9d3edca1c27','7da7ac7e-ad14-4056-acae-d621701fab8e',1,'runner-f35f3f83-c0ee-4ee5-9b9b-cb81a28e08a0',1,'2026-08-28 08:50:40.000000','2026-08-28 08:50:40.000000','2026-08-28 08:50:40.000000','dead_letter','unknown_job_type','no handler registered for e2.live.unknown','{\"schema_version\": 1}'),('e6bd8926-f4d8-4ff6-b56c-79d672bcc449','dc02f5cc-8f3b-4217-b006-a4cae7699566',2,'e2-fence-b',2,'2026-08-28 09:06:40.665836','2026-08-28 09:06:40.665836','2026-08-28 09:06:41.665836','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('ef2172be-9c19-4d7e-ace4-2d393d612b7c','434cfb34-fcc8-4c21-afa3-b426d715bbb6',1,'runner-6c4d5774-622a-40b6-b09e-0e312b4bdf77',1,'2026-08-28 08:53:08.000000','2026-08-28 08:53:08.000000','2026-08-28 08:53:08.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('f0fac4de-0c55-4de5-9d48-416193c1bde3','1f2e3e65-5a51-4187-a33d-de8f12e36305',1,'runner-f35f3f83-c0ee-4ee5-9b9b-cb81a28e08a0',1,'2026-08-28 08:50:40.000000','2026-08-28 08:50:40.000000','2026-08-28 08:50:40.000000','dead_letter','unknown_job_type','no handler registered for e2.restart.block','{\"schema_version\": 1}'),('f3f6692b-9f99-4eb2-b11d-22f2fd3caded','d8934d75-9a75-40e5-b24f-6bc7337cb3d4',1,'runner-6c4d5774-622a-40b6-b09e-0e312b4bdf77',1,'2026-08-28 08:53:08.000000','2026-08-28 08:53:08.000000','2026-08-28 08:53:08.000000','dead_letter','unknown_job_type','no handler registered for e2.live.unknown','{\"schema_version\": 1}'),('faf3d73d-6c65-432f-8d55-b42da0284fd3','8fa937ba-8f77-47cd-9cd6-129ffff460dc',1,'runner-b425b0cc-a0d3-45fb-9894-f53ea707bf42',1,'2026-08-28 09:06:27.000000','2026-08-28 09:06:27.000000','2026-08-28 09:06:27.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}'),('fc5ec6af-d491-482e-8932-eab36a82a63b','bdac56dc-a822-4da7-b44d-bc9a0c9a32e8',1,'runner-4a9b0823-97e7-4fb5-838d-c2d09560e2ed',1,'2026-08-28 09:02:42.000000','2026-08-28 09:02:42.000000','2026-08-28 09:02:42.000000','cancelled','cancel_requested','job cancellation was requested before the handler completed','{\"schema_version\": 1}'),('fd910b3c-b39f-4285-8861-1d3a07f3d8ef','6dbbe917-0a7b-414c-8093-85be64438425',2,'runner-47e2fe9a-9e64-414d-a1d1-1f01902e5d83',2,'2026-08-28 09:00:32.000000','2026-08-28 09:00:32.000000','2026-08-28 09:00:32.000000','succeeded',NULL,NULL,'{\"schema_version\": 1}');
/*!40000 ALTER TABLE `job_attempts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `jobs`
--

DROP TABLE IF EXISTS `jobs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `jobs` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `job_type` varchar(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `owner_scope_type` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `owner_scope_id` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `correlation_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `idempotency_key` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `payload_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `payload_json` json NOT NULL,
  `payload_schema_version` int NOT NULL,
  `status` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'queued',
  `priority` int NOT NULL DEFAULT '0',
  `available_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `attempt_count` int NOT NULL DEFAULT '0',
  `max_attempts` int NOT NULL DEFAULT '5',
  `lease_owner` varchar(128) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `lease_expires_at` datetime(6) DEFAULT NULL,
  `heartbeat_at` datetime(6) DEFAULT NULL,
  `fencing_token` bigint NOT NULL DEFAULT '0',
  `cancel_requested_at` datetime(6) DEFAULT NULL,
  `cancel_reason` varchar(4096) DEFAULT NULL,
  `cancelled_at` datetime(6) DEFAULT NULL,
  `result_json` json DEFAULT NULL,
  `result_schema_version` int DEFAULT NULL,
  `error_code` varchar(64) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `error_detail` text,
  `completed_at` datetime(6) DEFAULT NULL,
  `replay_of_job_id` char(36) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_jobs_idempotency_scope` (`job_type`,`owner_scope_type`,`owner_scope_id`,`idempotency_key`),
  KEY `replay_of_job_id` (`replay_of_job_id`),
  KEY `ix_jobs_claim` (`status`,`available_at`,`priority`,`created_at`,`id`),
  KEY `ix_jobs_owner_status` (`owner_scope_type`,`owner_scope_id`,`job_type`,`status`),
  KEY `ix_jobs_lease_expiry` (`status`,`lease_expires_at`),
  KEY `ix_jobs_correlation` (`correlation_id`),
  CONSTRAINT `jobs_ibfk_1` FOREIGN KEY (`replay_of_job_id`) REFERENCES `jobs` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_jobs_attempts` CHECK (((`attempt_count` >= 0) and (`max_attempts` > 0) and (`attempt_count` <= `max_attempts`))),
  CONSTRAINT `ck_jobs_fencing_token` CHECK ((`fencing_token` >= 0)),
  CONSTRAINT `ck_jobs_id_uuid` CHECK (regexp_like(`id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_jobs_payload_digest` CHECK (regexp_like(`payload_digest`,_ascii'^[0-9a-f]{64}$')),
  CONSTRAINT `ck_jobs_status` CHECK ((`status` in (_ascii'queued',_ascii'leased',_ascii'running',_ascii'retry_wait',_ascii'cancel_requested',_ascii'succeeded',_ascii'cancelled',_ascii'dead_letter')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `jobs`
--

LOCK TABLES `jobs` WRITE;
/*!40000 ALTER TABLE `jobs` DISABLE KEYS */;
INSERT INTO `jobs` VALUES ('0076fb7a-4121-40ff-b01d-d174e8d91a7a','e2.live.pressure','e2-pressure','e2-live-1787907986','fe3d9afe-e99f-4b58-8249-75990660eb6b','e2-live-1787907986-pressure-1','681ef90839c6f897325c95239268c45f29fb4d23ae63b7fc1f1bb7e37c46f0ed','{\"value\": \"one\", \"schema_version\": 1}',1,'cancelled',0,'2026-08-28 09:06:32.000000',0,5,NULL,NULL,NULL,0,'2026-08-28 09:06:32.000000','synthetic backpressure cleanup','2026-08-28 09:06:32.000000',NULL,NULL,NULL,NULL,'2026-08-28 09:06:32.000000',NULL,'2026-08-28 09:06:32.830437','2026-08-28 09:06:32.000000'),('07e5fc05-e305-4281-9ae6-ec9cd26e576e','e2.live.retry','e2-live','e2-live-1787907760','dada6dc4-4c38-45a4-abce-9e0d593fb250','e2-live-1787907760-retry','8fbed32134bbef3538079dd3f443629eb3708208025344d24b6501b64edeec59','{\"value\": \"retry\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 09:02:47.000000',2,5,NULL,NULL,NULL,2,NULL,NULL,NULL,'{\"retry\": \"succeeded\", \"attempt\": 2, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 09:02:47.000000',NULL,'2026-08-28 09:02:41.563770','2026-08-28 09:02:47.000000'),('08e3e7a5-1557-42bb-a6db-622f7739417e','e2.live.unknown','e2-live','e2-live-1787908484','9fb8ce83-571c-47b4-98b3-44d0e9236e0b','e2-live-1787908484-unknown','073fd96e2966d29f69cbbf3303aeb53f654eab14bab37acb1c7e04a52b85ddd3','{\"value\": \"unknown\", \"schema_version\": 1}',1,'dead_letter',0,'2026-08-28 09:14:43.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,NULL,NULL,'unknown_job_type','no handler registered for e2.live.unknown','2026-08-28 09:14:43.000000',NULL,'2026-08-28 09:14:43.712417','2026-08-28 09:14:43.000000'),('1f2e3e65-5a51-4187-a33d-de8f12e36305','e2.restart.block','e2-live','e2-live-1787907001-restart','dc557fc6-db88-4021-a465-3d7824b61ceb','e2-live-1787907001-restart-restart','686a022a7f742e639e23453dd0ff416b67d70c3b1f24a9e1357076866c3068bb','{\"value\": \"restart\", \"schema_version\": 1}',1,'dead_letter',0,'2026-08-28 08:50:06.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,NULL,NULL,'unknown_job_type','no handler registered for e2.restart.block','2026-08-28 08:50:40.000000',NULL,'2026-08-28 08:50:06.930563','2026-08-28 08:50:40.000000'),('223f5b9c-0c2d-4c2e-826e-b2f520bc0f4b','e2.live.pressure','e2-pressure','e2-live-1787907001','7b9b1a01-58af-499a-864c-a6c21812cffd','e2-live-1787907001-pressure-1','681ef90839c6f897325c95239268c45f29fb4d23ae63b7fc1f1bb7e37c46f0ed','{\"value\": \"one\", \"schema_version\": 1}',1,'cancelled',0,'2026-08-28 08:50:06.000000',0,5,NULL,NULL,NULL,0,'2026-08-28 08:50:06.000000','synthetic backpressure cleanup','2026-08-28 08:50:06.000000',NULL,NULL,NULL,NULL,'2026-08-28 08:50:06.000000',NULL,'2026-08-28 08:50:06.851847','2026-08-28 08:50:06.000000'),('2ba78a8c-6e99-45f1-b645-c0dc18bd455c','e2.live.pressure','e2-pressure','e2-live-1787908484','6c1e0052-5f90-416f-bcb6-a89b9b147968','e2-live-1787908484-pressure-1','681ef90839c6f897325c95239268c45f29fb4d23ae63b7fc1f1bb7e37c46f0ed','{\"value\": \"one\", \"schema_version\": 1}',1,'cancelled',0,'2026-08-28 09:14:49.000000',0,5,NULL,NULL,NULL,0,'2026-08-28 09:14:49.000000','synthetic backpressure cleanup','2026-08-28 09:14:49.000000',NULL,NULL,NULL,NULL,'2026-08-28 09:14:49.000000',NULL,'2026-08-28 09:14:49.855858','2026-08-28 09:14:49.000000'),('37818753-632e-41e4-b680-31e9213beb77','e2.live.pressure','e2-pressure','e2-live-1787907760','834484d6-2ec1-47d0-b3cc-a413ba419a29','e2-live-1787907760-pressure-1','681ef90839c6f897325c95239268c45f29fb4d23ae63b7fc1f1bb7e37c46f0ed','{\"value\": \"one\", \"schema_version\": 1}',1,'cancelled',0,'2026-08-28 09:02:47.000000',0,5,NULL,NULL,NULL,0,'2026-08-28 09:02:47.000000','synthetic backpressure cleanup','2026-08-28 09:02:47.000000',NULL,NULL,NULL,NULL,'2026-08-28 09:02:47.000000',NULL,'2026-08-28 09:02:47.748326','2026-08-28 09:02:47.000000'),('3b05aadf-8c73-45f5-a5c4-58a6e9f49869','e2.live.cancel','e2-live','e2-live-1787907001','d1a64cef-bcf8-4d8b-b171-31d7a6c107be','e2-live-1787907001-cancel','34e07b5a8b614f9f38103a34c9d1ab89b5dc0d4e109face7c5008f940144c3ff','{\"value\": \"cancel\", \"schema_version\": 1}',1,'cancelled',0,'2026-08-28 08:50:01.000000',1,5,NULL,NULL,NULL,1,'2026-08-28 08:50:01.000000','synthetic live cancellation','2026-08-28 08:50:01.000000',NULL,NULL,'cancel_requested','job cancellation was requested before the handler completed','2026-08-28 08:50:01.000000',NULL,'2026-08-28 08:50:01.156240','2026-08-28 08:50:01.000000'),('3ee6574e-1e12-43f3-9d95-164f4bf33f10','e2.live.retry','e2-live','e2-live-1787907041','4a43d51b-0c01-43a9-9f75-b048089a5de5','e2-live-1787907041-retry','8fbed32134bbef3538079dd3f443629eb3708208025344d24b6501b64edeec59','{\"value\": \"retry\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 08:50:46.000000',2,5,NULL,NULL,NULL,2,NULL,NULL,NULL,'{\"retry\": \"succeeded\", \"attempt\": 2, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 08:50:46.000000',NULL,'2026-08-28 08:50:40.409987','2026-08-28 08:50:46.000000'),('3eebd495-227e-42fa-bbb6-9d6f0af097cc','e2.restart.block','e2-live','e2-live-1787907760-restart','4da191b1-a36b-436c-8cd1-f3d445a6e85e','e2-live-1787907760-restart-restart','686a022a7f742e639e23453dd0ff416b67d70c3b1f24a9e1357076866c3068bb','{\"value\": \"restart\", \"schema_version\": 1}',1,'cancelled',0,'2026-08-28 09:02:47.000000',0,5,NULL,NULL,NULL,0,'2026-08-28 09:05:23.000000','failed live probe fixture cleanup','2026-08-28 09:05:23.000000',NULL,NULL,NULL,NULL,'2026-08-28 09:05:23.000000',NULL,'2026-08-28 09:02:47.824707','2026-08-28 09:05:23.000000'),('40469f02-80d4-4d5f-8c3b-ae0ac6a31cda','e2.live.retry','e2-live','e2-live-1787907001','bbda1cee-17ec-4b71-96aa-714633a8f64b','e2-live-1787907001-retry','8fbed32134bbef3538079dd3f443629eb3708208025344d24b6501b64edeec59','{\"value\": \"retry\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 08:50:06.000000',2,5,NULL,NULL,NULL,2,NULL,NULL,NULL,'{\"retry\": \"succeeded\", \"attempt\": 2, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 08:50:06.000000',NULL,'2026-08-28 08:50:01.148180','2026-08-28 08:50:06.000000'),('434cfb34-fcc8-4c21-afa3-b426d715bbb6','e2.echo','e2-live','e2-live-1787907041','5e508fa9-f644-41ba-bce2-3ff477a31ed7','e2-live-1787907041-fence','4f30e231ae41e716923ef480d9bf7309a628bb0795bfa34265737ef6beec8941','{\"value\": \"fence\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 08:50:46.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,'{\"echo\": {\"value\": \"fence\", \"schema_version\": 1}, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 08:53:08.000000',NULL,'2026-08-28 08:50:46.691695','2026-08-28 08:53:08.000000'),('453a662e-c61c-45ed-843f-1677589f79c4','e2.restart.block','e2-live','e2-live-1787907986-restart','568738ea-af5f-49d2-b2f3-f9edd845fc92','e2-live-1787907986-restart-restart','686a022a7f742e639e23453dd0ff416b67d70c3b1f24a9e1357076866c3068bb','{\"value\": \"restart\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 09:12:27.213085',2,5,NULL,NULL,NULL,2,NULL,NULL,NULL,'{\"debug\": 2, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 09:13:02.000000',NULL,'2026-08-28 09:06:32.907128','2026-08-28 09:13:02.000000'),('4806906c-559b-49aa-b418-2834f5d19559','e2.live.cancel','e2-live','e2-live-1787907188','9329167e-929a-4dab-9974-b8894fdfb097','e2-live-1787907188-cancel','34e07b5a8b614f9f38103a34c9d1ab89b5dc0d4e109face7c5008f940144c3ff','{\"value\": \"cancel\", \"schema_version\": 1}',1,'cancelled',0,'2026-08-28 08:53:08.000000',1,5,NULL,NULL,NULL,1,'2026-08-28 08:53:09.000000','synthetic live cancellation','2026-08-28 08:53:09.000000',NULL,NULL,'cancel_requested','job cancellation was requested before the handler completed','2026-08-28 08:53:09.000000',NULL,'2026-08-28 08:53:08.470518','2026-08-28 08:53:09.000000'),('4f8a8ecc-a8a0-49f0-9b78-ea8980ef929f','e2.echo','e2-live','e2-live-1787908484','ea1a97e9-9d0d-4eff-9317-186e91ca1cbb','e2-live-1787908484-echo','30d268b0236cff446ae4b96b861bd81d01a402550c20501ce303d6d02d0d4611','{\"value\": \"live-echo\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 09:14:43.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,'{\"echo\": {\"value\": \"live-echo\", \"schema_version\": 1}, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 09:14:43.000000',NULL,'2026-08-28 09:14:43.699322','2026-08-28 09:14:43.000000'),('52aaa47f-33a3-4fd8-8132-1ff031232e70','e2.live.unknown','e2-live','e2-live-1787907001','82de4ba5-6024-4733-99a3-7d3b270bc537','e2-live-1787907001-unknown','073fd96e2966d29f69cbbf3303aeb53f654eab14bab37acb1c7e04a52b85ddd3','{\"value\": \"unknown\", \"schema_version\": 1}',1,'dead_letter',0,'2026-08-28 08:50:01.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,NULL,NULL,'unknown_job_type','no handler registered for e2.live.unknown','2026-08-28 08:50:01.000000',NULL,'2026-08-28 08:50:01.138512','2026-08-28 08:50:01.000000'),('5a220335-bdeb-4201-89a8-43b64de84159','e2.live.unknown','e2-live','e2-live-1787907986','ffb19ea3-e520-41f2-82b4-3d8cba768ae7','e2-live-1787907986-unknown','073fd96e2966d29f69cbbf3303aeb53f654eab14bab37acb1c7e04a52b85ddd3','{\"value\": \"unknown\", \"schema_version\": 1}',1,'dead_letter',0,'2026-08-28 09:06:27.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,NULL,NULL,'unknown_job_type','no handler registered for e2.live.unknown','2026-08-28 09:06:27.000000',NULL,'2026-08-28 09:06:27.297542','2026-08-28 09:06:27.000000'),('5ffc8e31-43f5-43d6-9c45-75a34f526ef2','e2.live.cancel','e2-live','e2-live-1787907986','b83de93f-8297-4b36-be6d-eb8811669569','e2-live-1787907986-cancel','34e07b5a8b614f9f38103a34c9d1ab89b5dc0d4e109face7c5008f940144c3ff','{\"value\": \"cancel\", \"schema_version\": 1}',1,'cancelled',0,'2026-08-28 09:06:27.000000',1,5,NULL,NULL,NULL,1,'2026-08-28 09:06:27.000000','synthetic live cancellation','2026-08-28 09:06:27.000000',NULL,NULL,'cancel_requested','job cancellation was requested before the handler completed','2026-08-28 09:06:27.000000',NULL,'2026-08-28 09:06:27.312763','2026-08-28 09:06:27.000000'),('6acbc215-969e-40f4-a246-e24c2b5fa6bb','e2.echo','e2-live','e2-live-1787907188','000f885d-6dae-4e91-bbe0-a225f1aa42d6','e2-live-1787907188-fence','4f30e231ae41e716923ef480d9bf7309a628bb0795bfa34265737ef6beec8941','{\"value\": \"fence\", \"schema_version\": 1}',1,'succeeded',1000,'2026-08-28 08:53:22.114197',2,5,NULL,NULL,NULL,2,NULL,NULL,NULL,'{\"fenced\": \"accepted\", \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 08:53:24.114197',NULL,'2026-08-28 08:53:14.737071','2026-08-28 08:53:24.114197'),('6dbbe917-0a7b-414c-8093-85be64438425','e2.restart.block','e2-live','e2-live-1787907188-restart','2ab25bb0-cb69-469b-84ac-12fc3f014e6b','e2-live-1787907188-restart-restart','686a022a7f742e639e23453dd0ff416b67d70c3b1f24a9e1357076866c3068bb','{\"value\": \"restart\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 08:59:46.000000',2,5,NULL,NULL,NULL,2,NULL,NULL,NULL,'{\"attempt\": 2, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 09:00:32.000000',NULL,'2026-08-28 08:53:14.862594','2026-08-28 09:00:32.000000'),('71bec3d9-fd1b-42c7-b568-1d4cd89a7187','e2.live.retry','e2-live','e2-live-1787907188','5a5b0403-0ebb-4779-a4b4-2a52ad088633','e2-live-1787907188-retry','8fbed32134bbef3538079dd3f443629eb3708208025344d24b6501b64edeec59','{\"value\": \"retry\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 08:53:14.000000',2,5,NULL,NULL,NULL,2,NULL,NULL,NULL,'{\"retry\": \"succeeded\", \"attempt\": 2, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 08:53:14.000000',NULL,'2026-08-28 08:53:08.462433','2026-08-28 08:53:14.000000'),('7da7ac7e-ad14-4056-acae-d621701fab8e','e2.live.unknown','e2-live','e2-live-1787907041','07125c6e-d8ec-4f66-bdbd-5c31ac00e213','e2-live-1787907041-unknown','073fd96e2966d29f69cbbf3303aeb53f654eab14bab37acb1c7e04a52b85ddd3','{\"value\": \"unknown\", \"schema_version\": 1}',1,'dead_letter',0,'2026-08-28 08:50:40.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,NULL,NULL,'unknown_job_type','no handler registered for e2.live.unknown','2026-08-28 08:50:40.000000',NULL,'2026-08-28 08:50:40.401283','2026-08-28 08:50:40.000000'),('7fdfb197-f345-4864-a59c-4d2e787f3a4b','e2.echo','e2-live','e2-live-1787907001','54d1b008-af26-4a88-b570-dfd4145cc982','e2-live-1787907001-echo','30d268b0236cff446ae4b96b861bd81d01a402550c20501ce303d6d02d0d4611','{\"value\": \"live-echo\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 08:50:01.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,'{\"echo\": {\"value\": \"live-echo\", \"schema_version\": 1}, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 08:50:01.000000',NULL,'2026-08-28 08:50:01.123382','2026-08-28 08:50:01.000000'),('8bc7774a-bb4b-4b70-87fa-1c50e1d9e803','e2.echo','e2-live','e2-live-1787907001','26224654-9f6b-4861-a1e1-3ca4cbd6f710','e2-live-1787907001-fence','4f30e231ae41e716923ef480d9bf7309a628bb0795bfa34265737ef6beec8941','{\"value\": \"fence\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 08:50:14.575919',2,5,NULL,NULL,NULL,2,NULL,NULL,NULL,'{\"fenced\": \"accepted\", \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 08:50:16.575919',NULL,'2026-08-28 08:50:06.799030','2026-08-28 08:50:16.575919'),('8d723d99-797d-4084-854a-3a671b896635','e2.live.pressure','e2-pressure','e2-live-1787907188','68e8831c-12ec-423b-8b92-91f9c46c7d77','e2-live-1787907188-pressure-1','681ef90839c6f897325c95239268c45f29fb4d23ae63b7fc1f1bb7e37c46f0ed','{\"value\": \"one\", \"schema_version\": 1}',1,'cancelled',0,'2026-08-28 08:53:14.000000',0,5,NULL,NULL,NULL,0,'2026-08-28 08:53:14.000000','synthetic backpressure cleanup','2026-08-28 08:53:14.000000',NULL,NULL,NULL,NULL,'2026-08-28 08:53:14.000000',NULL,'2026-08-28 08:53:14.786034','2026-08-28 08:53:14.000000'),('8fa937ba-8f77-47cd-9cd6-129ffff460dc','e2.echo','e2-live','e2-live-1787907986','4867c5a6-adc2-4752-891d-c031b8f3d6b9','e2-live-1787907986-echo','30d268b0236cff446ae4b96b861bd81d01a402550c20501ce303d6d02d0d4611','{\"value\": \"live-echo\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 09:06:27.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,'{\"echo\": {\"value\": \"live-echo\", \"schema_version\": 1}, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 09:06:27.000000',NULL,'2026-08-28 09:06:27.284815','2026-08-28 09:06:27.000000'),('a8e99039-8b40-4a9e-9853-968f9c0f6b15','e2.live.retry','e2-live','e2-live-1787907986','f1cd4859-7128-4ded-84de-11a847f905a4','e2-live-1787907986-retry','8fbed32134bbef3538079dd3f443629eb3708208025344d24b6501b64edeec59','{\"value\": \"retry\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 09:06:32.000000',2,5,NULL,NULL,NULL,2,NULL,NULL,NULL,'{\"retry\": \"succeeded\", \"attempt\": 2, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 09:06:32.000000',NULL,'2026-08-28 09:06:27.304973','2026-08-28 09:06:32.000000'),('ad4debac-1ef3-40dc-b45e-a58f4797b363','e2.echo','e2-live','e2-live-1787907760','3a779de4-dcb9-4bb0-9452-ee80d5f299a9','e2-live-1787907760-echo','30d268b0236cff446ae4b96b861bd81d01a402550c20501ce303d6d02d0d4611','{\"value\": \"live-echo\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 09:02:41.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,'{\"echo\": {\"value\": \"live-echo\", \"schema_version\": 1}, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 09:02:41.000000',NULL,'2026-08-28 09:02:41.542856','2026-08-28 09:02:41.000000'),('b05c9ec6-98bb-45d8-ba5f-d0831c19f541','e2.echo','e2-live','e2-live-1787908484','ef27f62b-ae9c-45d1-8c25-37bd454109a6','e2-live-1787908484-fence','4f30e231ae41e716923ef480d9bf7309a628bb0795bfa34265737ef6beec8941','{\"value\": \"fence\", \"schema_version\": 1}',1,'succeeded',1000,'2026-08-28 09:14:57.791816',2,5,NULL,NULL,NULL,2,NULL,NULL,NULL,'{\"fenced\": \"accepted\", \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 09:14:59.791816',NULL,'2026-08-28 09:14:49.803422','2026-08-28 09:14:59.791816'),('b20b2caa-4963-4001-9498-940e2ed50536','e2.echo','e2-live','e2-live-1787907041','9af42a37-9d9f-45e3-813c-33b3d0a78e11','e2-live-1787907041-echo','30d268b0236cff446ae4b96b861bd81d01a402550c20501ce303d6d02d0d4611','{\"value\": \"live-echo\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 08:50:40.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,'{\"echo\": {\"value\": \"live-echo\", \"schema_version\": 1}, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 08:50:40.000000',NULL,'2026-08-28 08:50:40.388090','2026-08-28 08:50:40.000000'),('bdac56dc-a822-4da7-b44d-bc9a0c9a32e8','e2.live.cancel','e2-live','e2-live-1787907760','ae5e4fe9-fd6c-4f55-a3d5-c013b758b16f','e2-live-1787907760-cancel','34e07b5a8b614f9f38103a34c9d1ab89b5dc0d4e109face7c5008f940144c3ff','{\"value\": \"cancel\", \"schema_version\": 1}',1,'cancelled',0,'2026-08-28 09:02:41.000000',1,5,NULL,NULL,NULL,1,'2026-08-28 09:02:42.000000','synthetic live cancellation','2026-08-28 09:02:42.000000',NULL,NULL,'cancel_requested','job cancellation was requested before the handler completed','2026-08-28 09:02:42.000000',NULL,'2026-08-28 09:02:41.571863','2026-08-28 09:02:42.000000'),('c3e8650c-22e9-41b5-a97e-dee5e4af8368','e2.echo','e2-live','e2-live-1787907760','bf52915c-3455-44bb-9875-34f531281cb7','e2-live-1787907760-fence','4f30e231ae41e716923ef480d9bf7309a628bb0795bfa34265737ef6beec8941','{\"value\": \"fence\", \"schema_version\": 1}',1,'succeeded',1000,'2026-08-28 09:02:54.636198',2,5,NULL,NULL,NULL,2,NULL,NULL,NULL,'{\"fenced\": \"accepted\", \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 09:02:56.636198',NULL,'2026-08-28 09:02:47.694229','2026-08-28 09:02:56.636198'),('cb0c8ef3-b3ef-465d-937f-9560fa75b30d','e2.live.retry','e2-live','e2-live-1787908484','5c6811b3-3f89-4b75-b87f-747480e73fac','e2-live-1787908484-retry','8fbed32134bbef3538079dd3f443629eb3708208025344d24b6501b64edeec59','{\"value\": \"retry\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 09:14:49.000000',2,5,NULL,NULL,NULL,2,NULL,NULL,NULL,'{\"retry\": \"succeeded\", \"attempt\": 2, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 09:14:49.000000',NULL,'2026-08-28 09:14:43.721416','2026-08-28 09:14:49.000000'),('cb52ec86-33a8-4740-b5be-ada42af7d936','e2.restart.block','e2-live','e2-live-1787908484-restart','20cf0f20-8335-45e4-a90c-2806aea620bd','e2-live-1787908484-restart-restart','686a022a7f742e639e23453dd0ff416b67d70c3b1f24a9e1357076866c3068bb','{\"value\": \"restart\", \"schema_version\": 1}',1,'cancelled',0,'2026-08-28 09:26:16.000000',1,5,NULL,NULL,NULL,1,'2026-08-28 09:26:11.000000','close abandoned E2 probe fixture after lease recovery','2026-08-28 09:26:11.000000',NULL,NULL,'lease_expired',NULL,'2026-08-28 09:26:11.000000',NULL,'2026-08-28 09:14:49.931704','2026-08-28 09:26:11.000000'),('cdf1cc2a-9914-4041-bffa-d1ca7ba8cbe4','e2.echo','e2-live','e2-live-1787907188','c53a45e4-e645-458e-937f-d359929b0ec3','e2-live-1787907188-echo','30d268b0236cff446ae4b96b861bd81d01a402550c20501ce303d6d02d0d4611','{\"value\": \"live-echo\", \"schema_version\": 1}',1,'succeeded',0,'2026-08-28 08:53:08.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,'{\"echo\": {\"value\": \"live-echo\", \"schema_version\": 1}, \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 08:53:08.000000',NULL,'2026-08-28 08:53:08.440522','2026-08-28 08:53:08.000000'),('d8934d75-9a75-40e5-b24f-6bc7337cb3d4','e2.live.unknown','e2-live','e2-live-1787907188','f1a78fda-2d8c-40c4-ba70-bb0dd23fe20b','e2-live-1787907188-unknown','073fd96e2966d29f69cbbf3303aeb53f654eab14bab37acb1c7e04a52b85ddd3','{\"value\": \"unknown\", \"schema_version\": 1}',1,'dead_letter',0,'2026-08-28 08:53:08.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,NULL,NULL,'unknown_job_type','no handler registered for e2.live.unknown','2026-08-28 08:53:08.000000',NULL,'2026-08-28 08:53:08.454333','2026-08-28 08:53:08.000000'),('dc02f5cc-8f3b-4217-b006-a4cae7699566','e2.echo','e2-live','e2-live-1787907986','6eac776b-43da-45b3-bae7-8220b73eabaf','e2-live-1787907986-fence','4f30e231ae41e716923ef480d9bf7309a628bb0795bfa34265737ef6beec8941','{\"value\": \"fence\", \"schema_version\": 1}',1,'succeeded',1000,'2026-08-28 09:06:39.665836',2,5,NULL,NULL,NULL,2,NULL,NULL,NULL,'{\"fenced\": \"accepted\", \"schema_version\": 1}',1,NULL,NULL,'2026-08-28 09:06:41.665836',NULL,'2026-08-28 09:06:32.780608','2026-08-28 09:06:41.665836'),('e250124f-ce80-4060-b4f8-4ed7bfebc64c','e2.live.cancel','e2-live','e2-live-1787907041','2fdd0ab9-20a1-48c3-9894-b533bbac5ad2','e2-live-1787907041-cancel','34e07b5a8b614f9f38103a34c9d1ab89b5dc0d4e109face7c5008f940144c3ff','{\"value\": \"cancel\", \"schema_version\": 1}',1,'cancelled',0,'2026-08-28 08:50:40.000000',1,5,NULL,NULL,NULL,1,'2026-08-28 08:50:41.000000','synthetic live cancellation','2026-08-28 08:50:41.000000',NULL,NULL,'cancel_requested','job cancellation was requested before the handler completed','2026-08-28 08:50:41.000000',NULL,'2026-08-28 08:50:40.418104','2026-08-28 08:50:41.000000'),('e8536c74-76ab-4356-bb60-7075a7692e22','e2.live.unknown','e2-live','e2-live-1787907760','990d1c8e-3278-4275-87d0-57228c1e8c63','e2-live-1787907760-unknown','073fd96e2966d29f69cbbf3303aeb53f654eab14bab37acb1c7e04a52b85ddd3','{\"value\": \"unknown\", \"schema_version\": 1}',1,'dead_letter',0,'2026-08-28 09:02:41.000000',1,5,NULL,NULL,NULL,1,NULL,NULL,NULL,NULL,NULL,'unknown_job_type','no handler registered for e2.live.unknown','2026-08-28 09:02:41.000000',NULL,'2026-08-28 09:02:41.555556','2026-08-28 09:02:41.000000'),('f05e5c5b-e702-4a7c-8e5b-8849e018a805','e2.live.cancel','e2-live','e2-live-1787908484','e554f8cb-b6e4-47e4-9e52-6895b01c13f4','e2-live-1787908484-cancel','34e07b5a8b614f9f38103a34c9d1ab89b5dc0d4e109face7c5008f940144c3ff','{\"value\": \"cancel\", \"schema_version\": 1}',1,'cancelled',0,'2026-08-28 09:14:43.000000',1,5,NULL,NULL,NULL,1,'2026-08-28 09:14:44.000000','synthetic live cancellation','2026-08-28 09:14:44.000000',NULL,NULL,'cancel_requested','job cancellation was requested before the handler completed','2026-08-28 09:14:44.000000',NULL,'2026-08-28 09:14:43.729119','2026-08-28 09:14:44.000000');
/*!40000 ALTER TABLE `jobs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `knowledge_source_documents`
--

DROP TABLE IF EXISTS `knowledge_source_documents`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `knowledge_source_documents` (
  `id` varchar(36) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `md5` varchar(32) NOT NULL,
  `filename` varchar(255) NOT NULL,
  `original_filename` varchar(255) NOT NULL,
  `file_ext` varchar(32) NOT NULL,
  `mime_type` varchar(255) NOT NULL,
  `file_size` int NOT NULL,
  `content_blob` longblob NOT NULL,
  `status` varchar(32) NOT NULL,
  `chunk_count` int NOT NULL,
  `embedding_type` varchar(32) NOT NULL,
  `embedding_provider` varchar(100) NOT NULL,
  `embedding_model` varchar(200) NOT NULL,
  `embedding_base_url` varchar(500) NOT NULL,
  `error_message` text,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_knowledge_source_user_md5` (`user_id`,`md5`),
  KEY `ix_knowledge_source_documents_md5` (`md5`),
  KEY `ix_knowledge_source_documents_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `knowledge_source_documents`
--

LOCK TABLES `knowledge_source_documents` WRITE;
/*!40000 ALTER TABLE `knowledge_source_documents` DISABLE KEYS */;
/*!40000 ALTER TABLE `knowledge_source_documents` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `memory_items`
--

DROP TABLE IF EXISTS `memory_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `memory_items` (
  `id` varchar(36) NOT NULL,
  `user_id` varchar(36) NOT NULL,
  `source_type` varchar(32) DEFAULT NULL,
  `source_id` varchar(36) DEFAULT NULL,
  `type` varchar(32) DEFAULT NULL,
  `title` varchar(255) NOT NULL,
  `content` text,
  `status` varchar(32) DEFAULT NULL,
  `priority` varchar(32) DEFAULT NULL,
  `due_at` datetime DEFAULT NULL,
  `remind_at` datetime DEFAULT NULL,
  `completed_at` datetime DEFAULT NULL,
  `archived_at` datetime DEFAULT NULL,
  `review_count` int DEFAULT NULL,
  `interval_days` int DEFAULT NULL,
  `metadata_json` text,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_memory_items_due_at` (`due_at`),
  KEY `ix_memory_items_source_type` (`source_type`),
  KEY `ix_memory_items_remind_at` (`remind_at`),
  KEY `ix_memory_items_status` (`status`),
  KEY `ix_memory_items_source_id` (`source_id`),
  KEY `ix_memory_items_priority` (`priority`),
  KEY `ix_memory_items_type` (`type`),
  KEY `ix_memory_items_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `memory_items`
--

LOCK TABLES `memory_items` WRITE;
/*!40000 ALTER TABLE `memory_items` DISABLE KEYS */;
/*!40000 ALTER TABLE `memory_items` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `migration_maps`
--

DROP TABLE IF EXISTS `migration_maps`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `migration_maps` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `migration_batch_id` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `source_system` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `entity_type` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `source_id` varchar(255) NOT NULL,
  `target_uuid` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `source_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `status` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'mapped',
  `error_detail` text,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_migration_maps_source` (`source_system`,`entity_type`,`source_id`),
  KEY `ix_migration_maps_batch_status` (`migration_batch_id`,`status`),
  KEY `ix_migration_maps_target` (`target_uuid`),
  CONSTRAINT `ck_migration_maps_id_uuid` CHECK (regexp_like(`id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_migration_maps_source_digest` CHECK (regexp_like(`source_digest`,_ascii'^[0-9a-f]{64}$')),
  CONSTRAINT `ck_migration_maps_status` CHECK ((`status` in (_ascii'mapped',_ascii'conflict',_ascii'error'))),
  CONSTRAINT `ck_migration_maps_target_uuid` CHECK (regexp_like(`target_uuid`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `migration_maps`
--

LOCK TABLES `migration_maps` WRITE;
/*!40000 ALTER TABLE `migration_maps` DISABLE KEYS */;
/*!40000 ALTER TABLE `migration_maps` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `note_templates`
--

DROP TABLE IF EXISTS `note_templates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `note_templates` (
  `id` varchar(36) NOT NULL,
  `user_id` varchar(36) NOT NULL,
  `name` varchar(100) NOT NULL,
  `icon` varchar(50) DEFAULT NULL,
  `category` varchar(50) DEFAULT NULL,
  `title` varchar(200) DEFAULT NULL,
  `content` text,
  `tags` json DEFAULT NULL,
  `is_default` tinyint(1) NOT NULL,
  `sort_order` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_note_templates_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `note_templates`
--

LOCK TABLES `note_templates` WRITE;
/*!40000 ALTER TABLE `note_templates` DISABLE KEYS */;
/*!40000 ALTER TABLE `note_templates` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `notes`
--

DROP TABLE IF EXISTS `notes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `notes` (
  `id` varchar(36) NOT NULL,
  `user_id` varchar(36) NOT NULL,
  `title` varchar(200) NOT NULL,
  `content` text NOT NULL,
  `tags` json DEFAULT NULL,
  `category` varchar(50) DEFAULT NULL,
  `is_pinned` tinyint(1) NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_notes_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notes`
--

LOCK TABLES `notes` WRITE;
/*!40000 ALTER TABLE `notes` DISABLE KEYS */;
/*!40000 ALTER TABLE `notes` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `rag_generation_heads`
--

DROP TABLE IF EXISTS `rag_generation_heads`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `rag_generation_heads` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `owner_scope_type` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `owner_scope_id` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `index_kind` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `active_generation_id` char(36) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `staging_generation_id` char(36) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `revision` bigint NOT NULL DEFAULT '1',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rag_generation_heads_owner_index` (`owner_scope_type`,`owner_scope_id`,`index_kind`),
  KEY `ix_rag_generation_heads_active` (`active_generation_id`),
  KEY `ix_rag_generation_heads_staging` (`staging_generation_id`),
  CONSTRAINT `rag_generation_heads_ibfk_1` FOREIGN KEY (`active_generation_id`) REFERENCES `rag_generations` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `rag_generation_heads_ibfk_2` FOREIGN KEY (`staging_generation_id`) REFERENCES `rag_generations` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_rag_generation_heads_id_uuid` CHECK (regexp_like(`id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_rag_generation_heads_revision` CHECK ((`revision` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `rag_generation_heads`
--

LOCK TABLES `rag_generation_heads` WRITE;
/*!40000 ALTER TABLE `rag_generation_heads` DISABLE KEYS */;
/*!40000 ALTER TABLE `rag_generation_heads` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `rag_generations`
--

DROP TABLE IF EXISTS `rag_generations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `rag_generations` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `owner_scope_type` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `owner_scope_id` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `index_kind` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `embedding_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `generation` bigint NOT NULL,
  `status` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'building',
  `config_json` json NOT NULL,
  `config_schema_version` int NOT NULL,
  `source_revision` bigint NOT NULL,
  `job_id` char(36) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `error_detail` text,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `ready_at` datetime(6) DEFAULT NULL,
  `retired_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rag_generations_owner_index_generation` (`owner_scope_type`,`owner_scope_id`,`index_kind`,`embedding_fingerprint`,`generation`),
  KEY `ix_rag_generations_owner_status` (`owner_scope_type`,`owner_scope_id`,`index_kind`,`status`),
  KEY `ix_rag_generations_job` (`job_id`),
  CONSTRAINT `rag_generations_ibfk_1` FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_rag_generations_fingerprint` CHECK (regexp_like(`embedding_fingerprint`,_ascii'^[0-9a-f]{64}$')),
  CONSTRAINT `ck_rag_generations_id_uuid` CHECK (regexp_like(`id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_rag_generations_status` CHECK ((`status` in (_ascii'building',_ascii'ready',_ascii'failed',_ascii'retired')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `rag_generations`
--

LOCK TABLES `rag_generations` WRITE;
/*!40000 ALTER TABLE `rag_generations` DISABLE KEYS */;
/*!40000 ALTER TABLE `rag_generations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `refresh_tokens`
--

DROP TABLE IF EXISTS `refresh_tokens`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `refresh_tokens` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `session_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `family_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `token_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `jti_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `parent_token_id` char(36) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `replaced_by_token_id` char(36) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `status` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'active',
  `revision` bigint NOT NULL DEFAULT '1',
  `issued_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `consumed_at` datetime(6) DEFAULT NULL,
  `expires_at` datetime(6) NOT NULL,
  `revoked_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_refresh_tokens_jti_digest` (`jti_digest`),
  UNIQUE KEY `uq_refresh_tokens_token_digest` (`token_digest`),
  KEY `parent_token_id` (`parent_token_id`),
  KEY `replaced_by_token_id` (`replaced_by_token_id`),
  KEY `ix_refresh_tokens_session_status` (`session_id`,`status`),
  KEY `ix_refresh_tokens_family_status` (`family_id`,`status`),
  KEY `ix_refresh_tokens_expires` (`status`,`expires_at`),
  CONSTRAINT `refresh_tokens_ibfk_1` FOREIGN KEY (`parent_token_id`) REFERENCES `refresh_tokens` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `refresh_tokens_ibfk_2` FOREIGN KEY (`replaced_by_token_id`) REFERENCES `refresh_tokens` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `refresh_tokens_ibfk_3` FOREIGN KEY (`session_id`) REFERENCES `auth_sessions` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_refresh_tokens_family_uuid` CHECK (regexp_like(`family_id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_refresh_tokens_id_uuid` CHECK (regexp_like(`id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_refresh_tokens_jti_digest` CHECK (regexp_like(`jti_digest`,_ascii'^[0-9a-f]{64}$')),
  CONSTRAINT `ck_refresh_tokens_status` CHECK ((`status` in (_ascii'active',_ascii'consumed',_ascii'revoked'))),
  CONSTRAINT `ck_refresh_tokens_token_digest` CHECK (regexp_like(`token_digest`,_ascii'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `refresh_tokens`
--

LOCK TABLES `refresh_tokens` WRITE;
/*!40000 ALTER TABLE `refresh_tokens` DISABLE KEYS */;
/*!40000 ALTER TABLE `refresh_tokens` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `role_bindings`
--

DROP TABLE IF EXISTS `role_bindings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `role_bindings` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `user_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `role_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `scope_type` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `scope_id` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `status` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'active',
  `revision` bigint NOT NULL DEFAULT '1',
  `effective_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `expires_at` datetime(6) DEFAULT NULL,
  `revoked_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_role_bindings_subject_scope` (`user_id`,`role_id`,`scope_type`,`scope_id`),
  KEY `role_id` (`role_id`),
  KEY `ix_role_bindings_user_status` (`user_id`,`status`),
  KEY `ix_role_bindings_scope_status` (`scope_type`,`scope_id`,`status`),
  CONSTRAINT `role_bindings_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `role_bindings_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_role_bindings_id_uuid` CHECK (regexp_like(`id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_role_bindings_status` CHECK ((`status` in (_ascii'active',_ascii'revoked')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `role_bindings`
--

LOCK TABLES `role_bindings` WRITE;
/*!40000 ALTER TABLE `role_bindings` DISABLE KEYS */;
/*!40000 ALTER TABLE `role_bindings` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `roles` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `name` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `description` varchar(512) NOT NULL,
  `status` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'active',
  `revision` bigint NOT NULL DEFAULT '1',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_roles_name` (`name`),
  CONSTRAINT `ck_roles_id_uuid` CHECK (regexp_like(`id`,_utf8mb4'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_roles_status` CHECK ((`status` in (_utf8mb4'active',_utf8mb4'disabled')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `roles`
--

LOCK TABLES `roles` WRITE;
/*!40000 ALTER TABLE `roles` DISABLE KEYS */;
/*!40000 ALTER TABLE `roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_aliases`
--

DROP TABLE IF EXISTS `skill_aliases`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_aliases` (
  `id` varchar(36) NOT NULL COMMENT 'UUID',
  `skill_id` varchar(36) NOT NULL,
  `alias_name` varchar(128) NOT NULL,
  `alias_type` varchar(32) NOT NULL DEFAULT 'legacy',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_skill_aliases_alias_name` (`alias_name`),
  UNIQUE KEY `uq_skill_aliases_skill_alias` (`skill_id`,`alias_name`),
  KEY `ix_skill_aliases_skill_id` (`skill_id`),
  CONSTRAINT `skill_aliases_ibfk_1` FOREIGN KEY (`skill_id`) REFERENCES `skills` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_aliases`
--

LOCK TABLES `skill_aliases` WRITE;
/*!40000 ALTER TABLE `skill_aliases` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_aliases` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_audit_events`
--

DROP TABLE IF EXISTS `skill_audit_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_audit_events` (
  `id` varchar(36) NOT NULL COMMENT 'UUID',
  `skill_id` varchar(36) DEFAULT NULL,
  `skill_version_id` varchar(36) DEFAULT NULL,
  `installation_id` varchar(36) DEFAULT NULL,
  `import_id` varchar(36) DEFAULT NULL,
  `actor_type` varchar(32) NOT NULL DEFAULT 'user',
  `actor_id` varchar(64) DEFAULT NULL,
  `action` varchar(64) NOT NULL,
  `target_type` varchar(32) NOT NULL,
  `target_id` varchar(64) DEFAULT NULL,
  `correlation_id` varchar(64) DEFAULT NULL,
  `before_state` json DEFAULT NULL,
  `after_state` json DEFAULT NULL,
  `details` json NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `import_id` (`import_id`),
  KEY `installation_id` (`installation_id`),
  KEY `skill_version_id` (`skill_version_id`),
  KEY `ix_skill_audit_events_action_created` (`action`,`created_at`),
  KEY `ix_skill_audit_events_actor_id` (`actor_id`),
  KEY `ix_skill_audit_events_correlation_id` (`correlation_id`),
  KEY `ix_skill_audit_events_skill_created` (`skill_id`,`created_at`),
  CONSTRAINT `skill_audit_events_ibfk_1` FOREIGN KEY (`import_id`) REFERENCES `skill_imports` (`id`) ON DELETE SET NULL,
  CONSTRAINT `skill_audit_events_ibfk_2` FOREIGN KEY (`installation_id`) REFERENCES `skill_installations` (`id`) ON DELETE SET NULL,
  CONSTRAINT `skill_audit_events_ibfk_3` FOREIGN KEY (`skill_id`) REFERENCES `skills` (`id`) ON DELETE SET NULL,
  CONSTRAINT `skill_audit_events_ibfk_4` FOREIGN KEY (`skill_version_id`) REFERENCES `skill_versions` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_audit_events`
--

LOCK TABLES `skill_audit_events` WRITE;
/*!40000 ALTER TABLE `skill_audit_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_audit_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_capability_grants`
--

DROP TABLE IF EXISTS `skill_capability_grants`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_capability_grants` (
  `id` varchar(36) NOT NULL COMMENT 'UUID',
  `installation_id` varchar(36) NOT NULL,
  `skill_version_id` varchar(36) NOT NULL,
  `grants` json NOT NULL,
  `revision` bigint NOT NULL DEFAULT '1',
  `granted_by` varchar(64) DEFAULT NULL,
  `revoked_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_skill_capability_grants_installation_version` (`installation_id`,`skill_version_id`),
  KEY `ix_skill_capability_grants_installation_id` (`installation_id`),
  KEY `ix_skill_capability_grants_skill_version_id` (`skill_version_id`),
  KEY `ix_skill_capability_grants_granted_by` (`granted_by`),
  KEY `ix_skill_capability_grants_version_revoked` (`skill_version_id`,`revoked_at`),
  CONSTRAINT `skill_capability_grants_ibfk_1` FOREIGN KEY (`installation_id`) REFERENCES `skill_installations` (`id`) ON DELETE CASCADE,
  CONSTRAINT `skill_capability_grants_ibfk_2` FOREIGN KEY (`skill_version_id`) REFERENCES `skill_versions` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_capability_grants`
--

LOCK TABLES `skill_capability_grants` WRITE;
/*!40000 ALTER TABLE `skill_capability_grants` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_capability_grants` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_imports`
--

DROP TABLE IF EXISTS `skill_imports`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_imports` (
  `id` varchar(36) NOT NULL COMMENT 'UUID',
  `requested_by` varchar(64) NOT NULL,
  `idempotency_key` varchar(128) NOT NULL,
  `request_archive_digest` varchar(64) NOT NULL COMMENT 'SHA-256 of the exact uploaded archive bytes',
  `source_kind` varchar(32) NOT NULL COMMENT 'upload/editor/legacy/system',
  `source_reference` varchar(500) DEFAULT NULL,
  `staged_storage_key` varchar(500) DEFAULT NULL,
  `package_digest` varchar(64) DEFAULT NULL,
  `package_size_bytes` bigint DEFAULT NULL,
  `discovered_canonical_name` varchar(128) DEFAULT NULL,
  `status` varchar(17) NOT NULL DEFAULT 'received',
  `diagnostics` json NOT NULL,
  `requested_capabilities` json NOT NULL,
  `target_revision` bigint DEFAULT NULL,
  `error_code` varchar(64) DEFAULT NULL,
  `error_message` text,
  `attempt_count` int NOT NULL DEFAULT '0',
  `skill_id` varchar(36) DEFAULT NULL,
  `skill_version_id` varchar(36) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `started_at` datetime DEFAULT NULL,
  `completed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_skill_imports_idempotency_key` (`idempotency_key`),
  KEY `ix_skill_imports_package_digest` (`package_digest`),
  KEY `ix_skill_imports_requested_by` (`requested_by`),
  KEY `ix_skill_imports_skill_id` (`skill_id`),
  KEY `ix_skill_imports_skill_version_id` (`skill_version_id`),
  KEY `ix_skill_imports_status_created` (`status`,`created_at`),
  CONSTRAINT `skill_imports_ibfk_1` FOREIGN KEY (`skill_id`) REFERENCES `skills` (`id`) ON DELETE SET NULL,
  CONSTRAINT `skill_imports_ibfk_2` FOREIGN KEY (`skill_version_id`) REFERENCES `skill_versions` (`id`) ON DELETE SET NULL,
  CONSTRAINT `skill_import_status` CHECK ((`status` in (_utf8mb4'received',_utf8mb4'staged',_utf8mb4'validation_queued',_utf8mb4'validating',_utf8mb4'rejected',_utf8mb4'quarantined',_utf8mb4'awaiting_approval',_utf8mb4'publishing',_utf8mb4'published',_utf8mb4'failed_retryable')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_imports`
--

LOCK TABLES `skill_imports` WRITE;
/*!40000 ALTER TABLE `skill_imports` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_imports` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_installations`
--

DROP TABLE IF EXISTS `skill_installations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_installations` (
  `id` varchar(36) NOT NULL COMMENT 'UUID',
  `skill_id` varchar(36) NOT NULL,
  `active_version_id` varchar(36) DEFAULT NULL,
  `draft_version_id` varchar(36) DEFAULT NULL,
  `scope_type` varchar(32) NOT NULL DEFAULT 'system',
  `scope_key` varchar(128) NOT NULL DEFAULT 'global',
  `status` varchar(8) NOT NULL DEFAULT 'disabled',
  `settings` json NOT NULL,
  `revision` bigint NOT NULL DEFAULT '1',
  `created_by` varchar(64) DEFAULT NULL,
  `updated_by` varchar(64) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_skill_installations_scope` (`skill_id`,`scope_type`,`scope_key`),
  KEY `fk_skill_installations_active_skill_version` (`skill_id`,`active_version_id`),
  KEY `fk_skill_installations_draft_skill_version` (`skill_id`,`draft_version_id`),
  KEY `ix_skill_installations_active_version_id` (`active_version_id`),
  KEY `ix_skill_installations_draft_version_id` (`draft_version_id`),
  KEY `ix_skill_installations_scope_status` (`scope_type`,`scope_key`,`status`),
  KEY `ix_skill_installations_skill_id` (`skill_id`),
  CONSTRAINT `fk_skill_installations_active_skill_version` FOREIGN KEY (`skill_id`, `active_version_id`) REFERENCES `skill_versions` (`skill_id`, `id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_skill_installations_draft_skill_version` FOREIGN KEY (`skill_id`, `draft_version_id`) REFERENCES `skill_versions` (`skill_id`, `id`) ON DELETE RESTRICT,
  CONSTRAINT `skill_installations_ibfk_1` FOREIGN KEY (`skill_id`) REFERENCES `skills` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `skill_installation_status` CHECK ((`status` in (_utf8mb4'enabled',_utf8mb4'disabled')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_installations`
--

LOCK TABLES `skill_installations` WRITE;
/*!40000 ALTER TABLE `skill_installations` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_installations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_package_uploads`
--

DROP TABLE IF EXISTS `skill_package_uploads`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_package_uploads` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `package_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `request_archive_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `original_size_bytes` bigint NOT NULL,
  `media_type` varchar(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'application/zip',
  `raw_archive` longblob NOT NULL,
  `uploaded_by` varchar(64) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_skill_package_uploads_request_digest` (`request_archive_digest`),
  KEY `ix_skill_package_uploads_package_created` (`package_id`,`created_at`),
  KEY `ix_skill_package_uploads_uploaded_by` (`uploaded_by`),
  CONSTRAINT `skill_package_uploads_ibfk_1` FOREIGN KEY (`package_id`) REFERENCES `skill_packages` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_skill_package_uploads_id_uuid` CHECK (regexp_like(`id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_skill_package_uploads_request_digest` CHECK (regexp_like(`request_archive_digest`,_ascii'^[0-9a-f]{64}$')),
  CONSTRAINT `ck_skill_package_uploads_size` CHECK (((`original_size_bytes` >= 0) and (`original_size_bytes` <= 67108864)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_package_uploads`
--

LOCK TABLES `skill_package_uploads` WRITE;
/*!40000 ALTER TABLE `skill_package_uploads` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_package_uploads` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_packages`
--

DROP TABLE IF EXISTS `skill_packages`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_packages` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `package_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `canonical_archive_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `canonical_size_bytes` bigint NOT NULL,
  `media_type` varchar(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'application/zip',
  `canonical_archive` longblob NOT NULL,
  `manifest_json` json NOT NULL,
  `manifest_schema_version` int NOT NULL,
  `created_by` varchar(64) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_skill_packages_archive_digest` (`canonical_archive_digest`),
  UNIQUE KEY `uq_skill_packages_package_digest` (`package_digest`),
  KEY `ix_skill_packages_created_by` (`created_by`),
  CONSTRAINT `ck_skill_packages_archive_digest` CHECK (regexp_like(`canonical_archive_digest`,_ascii'^[0-9a-f]{64}$')),
  CONSTRAINT `ck_skill_packages_id_uuid` CHECK (regexp_like(`id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_skill_packages_package_digest` CHECK (regexp_like(`package_digest`,_ascii'^[0-9a-f]{64}$')),
  CONSTRAINT `ck_skill_packages_size` CHECK (((`canonical_size_bytes` >= 0) and (`canonical_size_bytes` <= 67108864)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_packages`
--

LOCK TABLES `skill_packages` WRITE;
/*!40000 ALTER TABLE `skill_packages` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_packages` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_registry_events`
--

DROP TABLE IF EXISTS `skill_registry_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_registry_events` (
  `id` varchar(36) NOT NULL COMMENT 'UUID',
  `revision` bigint NOT NULL,
  `event_type` varchar(64) NOT NULL,
  `skill_id` varchar(36) DEFAULT NULL,
  `payload` json NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `processed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_skill_registry_events_revision` (`revision`),
  KEY `ix_skill_registry_events_skill_id` (`skill_id`),
  KEY `ix_skill_registry_events_processed_created` (`processed_at`,`created_at`),
  CONSTRAINT `skill_registry_events_ibfk_1` FOREIGN KEY (`skill_id`) REFERENCES `skills` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_registry_events`
--

LOCK TABLES `skill_registry_events` WRITE;
/*!40000 ALTER TABLE `skill_registry_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_registry_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_registry_state`
--

DROP TABLE IF EXISTS `skill_registry_state`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_registry_state` (
  `id` varchar(32) NOT NULL,
  `revision` bigint NOT NULL DEFAULT '0',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_registry_state`
--

LOCK TABLES `skill_registry_state` WRITE;
/*!40000 ALTER TABLE `skill_registry_state` DISABLE KEYS */;
INSERT INTO `skill_registry_state` VALUES ('global',0,'2026-08-28 08:33:57');
/*!40000 ALTER TABLE `skill_registry_state` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_run_bindings`
--

DROP TABLE IF EXISTS `skill_run_bindings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_run_bindings` (
  `run_id` varchar(64) NOT NULL,
  `session_id` varchar(64) DEFAULT NULL,
  `user_id` varchar(64) NOT NULL,
  `registry_revision` bigint NOT NULL,
  `skill_bindings` json NOT NULL,
  `effective_grants` json NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`run_id`),
  KEY `ix_skill_run_bindings_user_created` (`user_id`,`created_at`),
  KEY `ix_skill_run_bindings_session_created` (`session_id`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_run_bindings`
--

LOCK TABLES `skill_run_bindings` WRITE;
/*!40000 ALTER TABLE `skill_run_bindings` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_run_bindings` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_versions`
--

DROP TABLE IF EXISTS `skill_versions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_versions` (
  `id` varchar(36) NOT NULL COMMENT 'UUID',
  `skill_id` varchar(36) NOT NULL,
  `parent_version_id` varchar(36) DEFAULT NULL,
  `version_number` int NOT NULL,
  `package_format` varchar(15) NOT NULL,
  `schema_version` varchar(32) NOT NULL DEFAULT '1',
  `source` varchar(32) NOT NULL COMMENT 'import/editor/legacy/system',
  `package_digest` varchar(64) NOT NULL COMMENT 'Immutable SHA-256 digest',
  `storage_key` varchar(500) NOT NULL COMMENT 'Immutable canonical Storage object key',
  `package_size_bytes` bigint NOT NULL DEFAULT '0',
  `name` varchar(128) NOT NULL,
  `display_name` varchar(160) NOT NULL,
  `description` text NOT NULL,
  `manifest` json NOT NULL,
  `requested_capabilities` json NOT NULL,
  `status` varchar(11) NOT NULL DEFAULT 'draft',
  `created_by` varchar(64) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `published_at` datetime DEFAULT NULL,
  `retired_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_skill_versions_package_digest` (`package_digest`),
  UNIQUE KEY `uq_skill_versions_skill_id` (`skill_id`,`id`),
  UNIQUE KEY `uq_skill_versions_skill_number` (`skill_id`,`version_number`),
  UNIQUE KEY `uq_skill_versions_storage_key` (`storage_key`),
  KEY `ix_skill_versions_created_by` (`created_by`),
  KEY `ix_skill_versions_parent_version_id` (`parent_version_id`),
  KEY `ix_skill_versions_skill_id` (`skill_id`),
  KEY `ix_skill_versions_skill_status` (`skill_id`,`status`),
  KEY `ix_skill_versions_status` (`status`),
  CONSTRAINT `skill_versions_ibfk_1` FOREIGN KEY (`parent_version_id`) REFERENCES `skill_versions` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `skill_versions_ibfk_2` FOREIGN KEY (`skill_id`) REFERENCES `skills` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `skill_package_format` CHECK ((`package_format` = _utf8mb4'agent_skills_v1')),
  CONSTRAINT `skill_version_status` CHECK ((`status` in (_utf8mb4'draft',_utf8mb4'validating',_utf8mb4'ready',_utf8mb4'rejected',_utf8mb4'quarantined',_utf8mb4'retired')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_versions`
--

LOCK TABLES `skill_versions` WRITE;
/*!40000 ALTER TABLE `skill_versions` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_versions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skills`
--

DROP TABLE IF EXISTS `skills`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skills` (
  `id` varchar(36) NOT NULL COMMENT 'UUID',
  `canonical_name` varchar(128) NOT NULL COMMENT 'Stable canonical Skill name',
  `status` varchar(8) NOT NULL DEFAULT 'active',
  `created_by` varchar(64) DEFAULT NULL,
  `archived_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_skills_canonical_name` (`canonical_name`),
  KEY `ix_skills_created_by` (`created_by`),
  KEY `ix_skills_status` (`status`),
  CONSTRAINT `skill_lifecycle_status` CHECK ((`status` in (_utf8mb4'active',_utf8mb4'archived')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skills`
--

LOCK TABLES `skills` WRITE;
/*!40000 ALTER TABLE `skills` DISABLE KEYS */;
/*!40000 ALTER TABLE `skills` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `token_revocations`
--

DROP TABLE IF EXISTS `token_revocations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `token_revocations` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `scope_type` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `scope_key` varchar(160) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `token_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `session_id` char(36) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `user_id` char(36) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `token_version` bigint DEFAULT NULL,
  `reason` varchar(4096) NOT NULL,
  `correlation_id` char(36) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `expires_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_token_revocations_scope_key` (`scope_type`,`scope_key`),
  KEY `ix_token_revocations_user_created` (`user_id`,`created_at`),
  KEY `ix_token_revocations_session_created` (`session_id`,`created_at`),
  KEY `ix_token_revocations_expires` (`expires_at`),
  CONSTRAINT `token_revocations_ibfk_1` FOREIGN KEY (`session_id`) REFERENCES `auth_sessions` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `token_revocations_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_token_revocations_id_uuid` CHECK (regexp_like(`id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_token_revocations_scope` CHECK ((`scope_type` in (_ascii'token',_ascii'session',_ascii'user_version')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `token_revocations`
--

LOCK TABLES `token_revocations` WRITE;
/*!40000 ALTER TABLE `token_revocations` DISABLE KEYS */;
/*!40000 ALTER TABLE `token_revocations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_embedding_configs`
--

DROP TABLE IF EXISTS `user_embedding_configs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_embedding_configs` (
  `id` varchar(36) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `provider` varchar(100) NOT NULL,
  `model_type` varchar(32) NOT NULL,
  `model_name` varchar(200) NOT NULL,
  `base_url` varchar(500) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_user_embedding_config_user_id` (`user_id`),
  KEY `ix_user_embedding_configs_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_embedding_configs`
--

LOCK TABLES `user_embedding_configs` WRITE;
/*!40000 ALTER TABLE `user_embedding_configs` DISABLE KEYS */;
/*!40000 ALTER TABLE `user_embedding_configs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_model_configs`
--

DROP TABLE IF EXISTS `user_model_configs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_model_configs` (
  `id` varchar(36) NOT NULL,
  `user_id` varchar(64) NOT NULL,
  `model_type` varchar(32) NOT NULL,
  `provider` varchar(100) NOT NULL,
  `model_name` varchar(200) NOT NULL,
  `base_url` varchar(500) NOT NULL,
  `api_key_encrypted` varchar(2048) DEFAULT NULL,
  `is_default` tinyint(1) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_user_model_configs_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_model_configs`
--

LOCK TABLES `user_model_configs` WRITE;
/*!40000 ALTER TABLE `user_model_configs` DISABLE KEYS */;
/*!40000 ALTER TABLE `user_model_configs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `username` varchar(150) NOT NULL,
  `email_display` varchar(254) NOT NULL,
  `email_normalized` varchar(254) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `phone_display` varchar(32) DEFAULT NULL,
  `phone_e164` varchar(32) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `password_hash` varchar(255) NOT NULL,
  `status` varchar(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'active',
  `token_version` bigint NOT NULL DEFAULT '1',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `disabled_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_users_email_normalized` (`email_normalized`),
  UNIQUE KEY `uq_users_phone_e164` (`phone_e164`),
  KEY `ix_users_status_created` (`status`,`created_at`),
  CONSTRAINT `ck_users_id_uuid` CHECK (regexp_like(`id`,_ascii'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')),
  CONSTRAINT `ck_users_status` CHECK ((`status` in (_ascii'active',_ascii'disabled',_ascii'locked')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping events for database 'doki_e2'
--

--
-- Dumping routines for database 'doki_e2'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-08-28  9:28:19
