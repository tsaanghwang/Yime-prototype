# 布局改动锁

布局讨论不需要每次都从音元体系的历史重新讲起，但实现必须保留已经取得的约束。
本锁把这些约束变成可执行检查，防止再次从数据链中间直接写码或写键位。

## 受保护的数据链

```text
数字标调拼音
  -> SyllableEncodingPipeline / YinjieEncoder
  -> 首音段 + 第2至第4音元
  -> 4 个 Yinyuan ID
  -> runtime / canonical symbol
  -> 唯一的 Yinyuan ID -> vk_key 投影
```

前五步决定“这个拼音由哪些音元组成”，属于语义编码；最后一步才决定音元放在哪个
物理键位。布局试验只能改最后一步。

## 唯一布局真源与唯一入口

唯一布局真源是：

```text
internal_data/manual_key_layout.json
```

每次修改后只运行：

```bash
python tools/run_locked_layout_pipeline.py
```

也可以启动可视化试验工作台：

```powershell
scripts\layout_workbench.cmd
```

工作台中的草案只保存在内存。选中键位后直接选择 Yinyuan ID，界面立即交换并进入
试打草案；结构检查和试打不会修改正式布局。只有点击“保存布局并进入生成流程”才会
写入唯一真源并立即生效。如果生成链失败，工作台自动恢复保存前的正式布局。

试打区会明确显示词库连接状态、候选记录数、实际查询码字段及完整查询链。查询会按
当前数据库结构自动选择 `variable_yinyuan_code`、`primary_yime_code` 或 `yime_code`，
不会把字段不兼容静默显示成“没有候选”。

导出的 Rime schema 使用布局投影 SHA-256 的前 12 位生成主翻译器 `user_dict` 名称。
布局发生变化时会自动进入新的学习库命名空间，防止旧键码的候选学习记录混入当前
布局；旧 `.userdb` 不删除，仍可备份或另行迁移。

该入口会用固定摘要锁住语义注册表和 1727 条“拼音 → 四个 Yinyuan ID”结果，再生成
resolved layout、KLC、可视表及
Yinyuan ID crosswalk，最后重新闭锁。CI 和本地测试也会执行同一把锁。

## 布局改动允许做什么

- 在 `manual_key_layout.json` 中调整 Yinyuan ID 的 base/shift 键位。
- 重新生成所有派生产物。
- 修改只描述键位安排的布局文档。

## 布局改动禁止做什么

- 为某个拼音直接指定按键、四音元码或 Yinyuan ID 序列。
- 新增平行布局 JSON、紧凑 `yinyuan_id_to_key` 表或其他隐藏映射。
- 为布局迁就而修改音元语义真源、音节分解规则或语义注册表摘要。
- 手工修改 resolved layout、KLC、crosswalk 等派生产物。
- 向导出器传入另一套布局文件，从 canonical symbol 直接跳到按键。

若确实需要修改拼音分解或音元身份，那是独立的“语义改动”，应单独审查并更新语义
锁摘要；不得混入布局改动。

## 锁失败时

运行以下命令查看具体断点：

```bash
python tools/check_layout_change_lock.py
```

不要通过删除检查、添加补丁或更新摘要来消除错误；应回到错误指出的上游真源修复，
然后重新运行唯一入口。
