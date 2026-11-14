# 本地 MySQL 存储

## 当前连接

本机已于 2026-11-13 将原 SQLite 数据迁入 MySQL 8.0，并切换应用连接：

- 地址：`127.0.0.1:3306`
- 数据库：`ai_jobs_intelligence`
- 用户：`root`，密码留空
- 字符集：`utf8mb4`；表使用 InnoDB。

`.env` 配置如下（不提交 Git）：

```dotenv
DATABASE_URL=mysql+pymysql://root@127.0.0.1:3306/ai_jobs_intelligence?charset=utf8mb4
```

启动应用前应先启动 MySQL。页面仍使用 `http://127.0.0.1:8000/`，插件无需修改。岗位、正文、技能和采集批次读写 MySQL；原始 JSON 和采集日志仍在 `data/raw/extension/`。

本机 MySQL 的数据根目录为 `F:\MySQL\data\`，由 MySQL 管理。请用数据库客户端查看表，不直接编辑数据文件。

## 本次迁移记录

切换时迁移了 205 条岗位、48 条正文、384 条技能提及、76 个采集批次。按主键保留所有记录，逐表比较记录数及全部字段的 SHA-256 校验值，一致后提交事务。恢复采集后这些数量会继续增加。

原 `data/jobs.db` 保留不动；一致性快照及校验报告位于 `data/backups/`。SQLite 备份只代表切换时的数据，不包含此后写入 MySQL 的记录。

## 在另一台电脑迁移

1. 安装依赖：`backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt`。
2. 停止本项目后端，避免复制期间仍有 SQLite 写入。确认本地 MySQL 可连接。
3. 运行 `backend\.venv\Scripts\python.exe -B scripts/migrate_to_mysql.py`。
4. 确认输出 `verified: true`，再将 `.env` 改为上面的连接串，运行 `scripts/start.ps1`。

脚本默认从 `data/jobs.db` 读取，也支持 `--source`。目标连接可通过 `MYSQL_TARGET_URL` 环境变量配置。只支持本机 MySQL，且目标数据库必须不存在；已存在时拒绝执行，不覆盖、清空或重复导入。失败时保留 SQLite 和备份；如果已创建目标库，会保留其结构供排查，事务中的插入将回滚。修正后应选用新的目标数据库名重试。

如果迁移或启动失败，保持/恢复原 SQLite 连接并启动服务即可继续使用原数据。切换后若已向 MySQL 写入新数据，不能直接切回旧 SQLite 而期待两边自动同步。

## 备份与测试

MySQL 数据不会随 Git 推送上传。使用 `mysqldump --host=127.0.0.1 --port=3306 --user=root --skip-password --single-transaction --default-character-set=utf8mb4 --result-file=data/backups/mysql-backup.sql ai_jobs_intelligence` 导出一致性备份（先创建目录，使用独立文件名保留各次备份）。`--result-file` 避免 PowerShell 重定向改变 SQL 文件编码。

日常 `scripts/test.ps1` 仍使用隔离 SQLite。测试 MySQL 时，先创建全新的 `ai_jobs_test_*` 数据库，将连接串赋给 `MYSQL_TEST_URL`，再执行测试脚本。测试会创建并删除测试库中的项目表，严禁指向真实数据；脚本会检查本机地址和测试库名称前缀。

连接池与 MySQL 方言设置参考 [SQLAlchemy MySQL 文档](https://docs.sqlalchemy.org/en/20/dialects/mysql.html)。正文使用 LONGTEXT，时间使用 DATETIME(6)，保留长篇中文和微秒；连接启用存活检测和空闲连接回收。
