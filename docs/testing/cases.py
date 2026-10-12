# 测试用例数据。每条：(模块, 功能点, 优先级, 前置条件, 操作步骤, 预期结果, 老系统要求, 对照)
# 对照：同等 = 与老系统一致；增强 = 满足老系统且更多；差异 = 已决定的有意改变；
#       待确认 = 代码里没看到老系统的这条规则，测试时重点确认；新增 = 老系统没有；不适用 = 老系统也没有

C = []


def add(mod, feat, pri, pre, steps, exp, old, cmp):
    C.append((mod, feat, pri, pre, steps, exp, old, cmp))


# ---------------- 登录与权限 ----------------
M = "登录与权限"
add(M, "正常登录", "P0", "已有管理员账号",
    "1. 打开系统地址（如 http://localhost:8080）\n2. 输入邮箱和密码，点登录",
    "进入 Home 页，左下角显示自己的名字",
    "§3 产品登录页登录", "同等")
add(M, "密码错误", "P0", "无",
    "1. 输入正确邮箱、错误密码，点登录",
    "提示登录失败，停留在登录页",
    "§3 产品登录页登录", "同等")
add(M, "连续失败锁定", "P2", "一个测试账号",
    "1. 用同一账号连续输错密码 9 次\n2. 再输入正确密码",
    "第 8 次之后账号被锁 15 分钟，正确密码也暂时无法登录",
    "老系统无此要求", "新增")
add(M, "退出登录", "P0", "已登录",
    "1. 点左下角退出图标\n2. 浏览器点后退，或直接访问 /home",
    "回到登录页；后退或直接访问都要求重新登录",
    "§3 退出", "同等")
add(M, "未登录访问受保护页面", "P0", "未登录",
    "1. 直接在地址栏打开 /clients 或某个看板地址",
    "被送回登录页；登录后回到刚才想去的页面",
    "§3 普通用户被送回 /smart", "同等")
add(M, "刷新保持登录", "P1", "已登录",
    "1. 在任意页面按 F5 刷新\n2. 关闭标签页再打开系统",
    "仍然是登录状态，不需要重新输入密码",
    "隐含要求", "同等")
add(M, "忘记密码（管理员重置）", "P1", "管理员账号 + 一个普通用户 A",
    "1. A 在另一个浏览器保持登录\n2. 管理员进 Users，给 A 设新密码\n3. A 刷新页面\n4. A 用新密码登录",
    "第 3 步 A 被登出（旧会话失效）；新密码可登录，旧密码不行",
    "§3 登录页有\"忘记密码\"自助流程", "差异")
add(M, "只开通一个产品线", "P0", "用户 B：只给 Accounting 的 member 角色",
    "1. 用 B 登录\n2. 看顶部产品线切换\n3. 手动把地址里的 /w/accounting/ 改成 /w/grants/",
    "B 只看到 Accounting；手动访问 Grants 看不到数据或被拒绝",
    "§3 只有 Smart Accounting User 才能进会计线，Grants 同理", "同等")
add(M, "列按产品线隔离", "P0", "无",
    "1. 打开 Accounting 任一看板，点 Columns 看可选列\n2. 打开 Grants 任一看板，同样查看",
    "Accounting 看不到 Grant Type、AP Submit Date 等 Grants 列；Grants 看不到 Lodgement Due、Monthly Status 等会计列",
    "§3 看板上的列按模块过滤", "同等")
add(M, "viewer 只读", "P1", "用户 C：Accounting 的 viewer 角色",
    "1. 用 C 登录，打开会计看板\n2. 双击单元格尝试修改\n3. 找 New 按钮、勾选行",
    "能看不能改：单元格不可编辑，没有新建按钮，勾选后没有批量操作",
    "老系统按 Frappe 读写权限，没有专门的只读角色", "增强")
add(M, "member 与 manager 的区别", "P1", "用户 B（member）",
    "1. 用 B 勾选一行，看批量栏有没有 Delete\n2. 打开 Automations 看能否新建规则\n3. 保存视图时看能否选 Shared",
    "member 不能删除项目、不能管理自动化、不能建共享视图；manager 可以",
    "§13 管自动化、看板设置需要管理员类角色", "增强")
add(M, "管理页面只对管理员开放", "P0", "用户 B（非管理员）",
    "1. 用 B 登录看左侧导航\n2. 直接访问 /users 和 /system",
    "导航里没有 Users、System health；直接访问看不到数据或被拒绝",
    "§13 管用户需要管理员", "同等")

# ---------------- Home 与导航 ----------------
M = "Home 与导航"
add(M, "我参与的项目", "P0", "用户 A 在两个项目里是 Preparer（一个会计、一个 Grants）",
    "1. 用 A 登录，看 Home",
    "两个项目都列出来，能看出属于哪条产品线、哪块看板",
    "§4 Home：当前用户参与的项目", "同等")
add(M, "按状态计数", "P0", "同上",
    "1. 看 Home 的状态条/计数\n2. 改其中一个项目的状态后回到 Home",
    "按状态显示数量，改状态后数字跟着变",
    "§4 Home：按状态的数量", "同等")
add(M, "从状态点进项目列表", "P1", "同上",
    "1. 在 Home 点某个状态",
    "列出该状态下我参与的项目，可以点进去",
    "§4 status-projects 视图：从 Home 按状态点进去", "待确认")
add(M, "30 天内到期", "P2", "一个项目 Lodgement Due 设为 10 天后，自己在团队里",
    "1. 看 Home",
    "该项目出现在\"30 天内到期\"里",
    "老系统没有", "新增")
add(M, "侧边栏结构", "P0", "管理员登录",
    "1. 依次查看左侧导航",
    "有 Home、该产品线的看板列表、Archived、Automations、Automation logs、Workspace setup、Data migration、Clients、Activity、Users、System health、Settings（左下角名字）",
    "§4 Home、Report、Boards、Archived Projects、Clients、Users、Archived Clients、Automation Logs、Settings", "同等")
add(M, "Report 页", "P2", "无",
    "1. 找 Report 入口",
    "新系统暂无 Report 页（已列入后续计划），记录即可",
    "§15 老系统 Report 也只是空页面", "不适用")
add(M, "产品线切换", "P0", "管理员（两条线都有权限）",
    "1. 点顶部 Accounting / Grants 切换",
    "侧边栏看板列表跟着切换：Accounting 9 块，Grants FY 2024–FY 2027",
    "§2 两条产品线，入口分开", "同等")
add(M, "界面语言", "P2", "无",
    "1. Settings 里把语言改成中文",
    "导航变成中文（其余页面暂时仍是英文，已知限制）",
    "老系统没有", "新增")

# ---------------- 客户 ----------------
M = "客户 Clients"
add(M, "搜索客户", "P0", "已有若干客户",
    "1. 进 Clients\n2. 输入客户名的一部分",
    "列表即时过滤出匹配的客户",
    "§5 搜索客户，看列表", "同等")
add(M, "新建客户（带主实体）", "P0", "无",
    "1. Clients → New client\n2. 填名称 \"Test Client A Pty Ltd\"、实体类型 Company、年结 June、ABN、负责合伙人\n3. 保存",
    "客户创建成功；打开后能看到一个主实体，类型、年结、ABN 正确，合伙人正确",
    "§16 新建客户：名称必填；带实体时实体名、类型、年结必填；写主实体和合伙人", "同等")
add(M, "客户名称必填", "P0", "无",
    "1. New client，名称留空直接保存",
    "不能保存，提示名称必填",
    "§16 客户名称必填", "同等")
add(M, "重名检查", "P0", "已有客户 \"Test Client A Pty Ltd\"",
    "1. 再新建同名客户\n2. 再试一个相似名称，如 \"Test Client A\"",
    "完全同名被拒绝；相似名称会提示可能重复，但允许继续",
    "§16 不能与已有客户重名", "增强")
add(M, "编辑客户", "P0", "已有客户",
    "1. 打开客户 Details\n2. 修改名称、实体类型、年结、负责合伙人\n3. 保存后刷新",
    "修改都保存成功",
    "§5 编辑客户名称、实体类型、年结、负责合伙人", "同等")
add(M, "多个实体", "P1", "已有客户",
    "1. 在客户下再加一个实体（如 Trust），填 ABN、ACN、年结\n2. 把新实体设为主实体",
    "两个实体都在；同一时间只有一个主实体",
    "§5 Customer Entity 子表：类型、ABN、年结、是否主实体", "增强")
add(M, "实体类型选项", "P1", "无",
    "1. 新建实体时查看类型下拉",
    "至少包含 Individual、Company、Partnership、Trust、Other Incorporated Entity",
    "§5 实体类型 5 个选项", "同等")
add(M, "联系人", "P1", "已有客户",
    "1. 给客户加两个联系人\n2. 一个标为主要联系人，一个标为账单联系人",
    "联系人保存成功，标记正确显示",
    "§5 Contact 字段在但客户页没有入口", "增强")
add(M, "推荐人", "P2", "已有客户和联系人",
    "1. 把某联系人标为推荐人（Referrer）",
    "保存成功，客户页能看到推荐人",
    "§15 推荐人字段在但没有界面", "增强")
add(M, "客户名下项目", "P0", "客户名下有会计和 Grants 项目各一个",
    "1. 打开客户 → Work 标签",
    "两个项目都列出来，能点进去",
    "§4 client-projects：某客户名下的项目", "同等")
add(M, "归档客户", "P0", "客户 X 有 2 个在看板上的项目，另有 1 个已手动归档的项目",
    "1. 归档客户 X\n2. 看 Clients 的 Archived 分组\n3. 看两个项目所在看板和 Archived 页",
    "X 出现在已归档客户里；2 个在用项目从看板消失，出现在 Archived，来源显示\"Client archived\"；这一步不触发自动化",
    "§16 归档客户：客户停用，名下在用项目一起归档，来源 Client Archive，不跑自动化", "同等")
add(M, "恢复客户", "P0", "接上一条",
    "1. 在 Archived 分组里恢复客户 X\n2. 查看三个项目",
    "因客户归档而归档的 2 个项目回到原看板；原本手动归档的那 1 个仍在 Archived",
    "§16 恢复只恢复当时一起归档的项目，手动归档的不打开", "同等")
add(M, "删除有项目的客户", "P0", "客户名下有项目",
    "1. 删除该客户",
    "被拒绝，并提示还有几个关联项目",
    "§16 有关联项目时拒绝删除并返回数量", "同等")
add(M, "删除无项目的客户", "P1", "一个没有任何项目的客户",
    "1. 删除该客户",
    "删除成功，列表里不再显示（可从 Activity 恢复）",
    "§16 无关联项目时删除", "增强")
add(M, "客户 Updates", "P2", "已有客户",
    "1. 客户页 → Updates，写一条留言",
    "留言保存并显示作者和时间",
    "老系统只有项目上有 Updates", "新增")
add(M, "客户 Activity", "P1", "改过客户资料",
    "1. 客户页 → Activity",
    "看到刚才的修改：谁、什么时候、改了什么",
    "§12 全局活动包含客户的更新", "同等")
add(M, "Grants 客户级字段同步到看板", "P0", "客户 X 在 FY 2026 看板上有项目",
    "1. 在客户 X 上改 Portal Access Received、Portal Access Expiry、State、Industry、地址、主要沟通方式\n2. 打开 FY 2026 看板",
    "看板上 X 那一行对应列立刻显示新值",
    "§5/§7 门户权限在客户保存时抄到项目上", "差异")
add(M, "看板上改客户级字段", "P1", "同上",
    "1. 在 Grants 看板上尝试直接改 Portal Access Expiry 这类镜像列",
    "按设计不在行上单独改，而是改客户（列为只读，或跳到客户页）。如果业务上需要\"某一行单独不同\"，请在备注里写出来",
    "§7 项目上那一份仍可以在看板里单独改", "差异")

# ---------------- Accounting 看板 ----------------
M = "Accounting 看板"
add(M, "看板列表", "P0", "无",
    "1. 切到 Accounting，看侧边栏",
    "有 Financials & Tax Return、ITR、BAS、Payroll、Payroll & Super、Bookkeeping、SMSF、Audit、Financial Statements",
    "§2 一种 Project Type 一块看板", "同等")
add(M, "字段齐全", "P0", "打开任一会计看板",
    "1. 点 Columns，逐个勾选显示",
    "能找到：Project Name、Client、Entity、Fiscal Year、Status、Lodgement Due、Company、Entity Type、Year End、Target Month、Frequency、Reset Date、Monthly Status、Software、ATO、LodgeIT、Company Agent、Xero/QuickBooks、Priority、Budget、Engagement Letter、Notes，以及 Preparer / Manager / Partner / Assigned Person",
    "§6 会计线全部标准字段和自定义字段", "同等")
add(M, "状态选项", "P0", "无",
    "1. 点任一行的 Status",
    "13 个：Not started、Working on it、Waiting for client、Ready for manager review、Review points to be actioned、Ready for partner review、Ready to send to client、Sent to client for signature、Waiting for CTR、Waiting for payment、Hold、Completed、Not to Proceed",
    "§10 状态池中会计用的部分", "同等")
add(M, "频率选项", "P1", "无",
    "1. 点 Frequency",
    "Yearly、Half-Yearly、Quarterly、Monthly、Fortnightly、Weekly、One-off",
    "§6 频率 7 个选项", "同等")
add(M, "12 个月完成状态", "P0", "一行项目",
    "1. 在 Monthly Status 里点几个月份格子\n2. 刷新页面",
    "每格可在 Not Started / Working On It / Stuck / Done 之间切换，颜色不同；刷新后保持",
    "§6 Monthly Status：每月一条状态，四个选项", "同等")
add(M, "软件（多选）", "P0", "一行项目",
    "1. 在 Software 选 Xero 和 MYOB\n2. 再去掉 MYOB",
    "多选正确保存",
    "§6 custom_softwares 子表", "同等")
add(M, "四个跟踪状态", "P1", "一行项目",
    "1. 分别改 ATO、LodgeIT、Company Agent、Xero/QuickBooks",
    "选项都是 Not started / Not applicable / Done，保存正确",
    "§6 四个跟踪状态字段", "同等")
add(M, "Entity Type 来自实体", "P1", "项目已关联实体",
    "1. 去客户页把实体类型从 Company 改成 Trust\n2. 回到看板",
    "该行 Entity Type 自动变成 Trust",
    "§6 实体类型展示用，从实体带出", "差异")
add(M, "团队角色", "P0", "一行项目",
    "1. 给这一行设置 Preparer、Manager、Assigned Person 各一人",
    "保存后显示人名；打开项目详情能看到分配日期",
    "§6 Project Team Member：用户、角色、分配日期", "同等")
add(M, "Engagement Letter", "P2", "一行项目",
    "1. 在 Engagement Letter 填一个网盘链接",
    "保存为链接，可点击打开。暂不支持上传文件（已知限制，等文件模块）",
    "§6 custom_engagement_letter 是附件", "差异")

# ---------------- Grants 看板 ----------------
M = "Grants 看板"
add(M, "看板列表", "P0", "无",
    "1. 切到 Grants，看侧边栏",
    "有 FY 2024、FY 2025、FY 2026、FY 2027，没有 Archived (Holding)",
    "§2 FY 2024–FY 2027 加 Archived (Holding)", "差异")
add(M, "客户列固定在左边", "P1", "打开 FY 2026",
    "1. 向右滚动表格\n2. 尝试把别的列拖到客户列左边",
    "客户列始终固定在最左",
    "§7 customer 固定在最左边", "同等")
add(M, "字段齐全", "P0", "打开 FY 2026",
    "1. 点 Columns，逐个勾选显示",
    "能找到：FY/CY、Grant Type、Grants Priority、Portal Access Received、Portal Access Expiry、Tax Agent、AP Submit Date、Industry Approval Date、Tax Lodgement Date、Contact Name、Primary Communication、ABN、State、Industry、Engagement Date、Rebate Amount、Fee Arrangement、Fee Percentage、Referral、Application Progress、Notes，以及 Responsible Person、Salesperson、Partner",
    "§7 Grants 全部自定义字段", "同等")
add(M, "状态选项", "P0", "无",
    "1. 点任一行 Status",
    "19 个，按申报顺序：Not started、Hold、Waiting for kickoff … Waiting for payment、Completed、Not to Proceed",
    "§10 Grants 使用按申报顺序排的一段", "同等")
add(M, "三个日期是真正的日期", "P0", "一行项目",
    "1. AP Submit Date 填 2026-09-11\n2. Industry Approval Date、Tax Lodgement Date 各填一个日期\n3. 按 AP Submit Date 排序",
    "用日期选择器输入；排序按时间先后，不按文字",
    "§7 三个日期在老系统是文字", "增强")
add(M, "选项字段", "P1", "一行项目",
    "1. 改 Grant Type、Grants Priority、FY/CY、Tax Agent",
    "Grant Type：R&DTI / EMDG；Priority：S1–S4（有颜色）；FY/CY：FY / CY；Tax Agent 是勾选",
    "§7 custom_grants_type、priority、tg_tax_agent", "同等")
add(M, "人员是系统用户", "P1", "已建好用户",
    "1. 在 Responsible Person、Salesperson、Partner 里选人",
    "从用户列表里选，不是自由文字；被选的人在 Home 能看到这个项目",
    "§7 合伙人、负责人在老系统是文字", "增强")
add(M, "ABN、联系人等来自客户", "P1", "客户有 ABN 和联系人",
    "1. 看该客户在 Grants 看板上的 ABN、Contact Name 列",
    "显示客户上的值",
    "§7 ABN、地址、联系人是项目上的快照", "差异")

# ---------------- 表格通用 ----------------
M = "看板表格（两条线通用）"
add(M, "大量行滚动", "P1", "看板上有 100 行以上（可用迁移导入样本）",
    "1. 打开看板，快速上下滚动",
    "流畅，没有空白或卡死",
    "§8 滚动查看，行多时分段加载", "同等")
add(M, "显示/隐藏列", "P0", "无",
    "1. Columns 里关掉 Notes，再打开",
    "列随之消失和出现",
    "§8 显示、隐藏列", "同等")
add(M, "列宽、列顺序", "P0", "无",
    "1. 拖动列边框改宽度\n2. 拖动列头换顺序",
    "宽度和顺序立即生效（保存成视图后刷新也保持）",
    "§8 调列宽和顺序", "同等")
add(M, "搜索", "P0", "无",
    "1. 在看板搜索框输入项目名或客户名的一部分",
    "只显示匹配的行",
    "§8 搜索项目名", "同等")
add(M, "排序", "P0", "无",
    "1. 点 Lodgement Due（或其他列）列头，再点一次",
    "升序、降序切换正确，空值位置一致",
    "§8 排序", "同等")
add(M, "高级筛选", "P0", "无",
    "1. 打开 Filter\n2. 条件：Status 是 Working on it 且 Priority 是 High\n3. 改成\"或\"\n4. 再加一条 Lodgement Due 在 14 天内\n5. 加一条 Preparer 是\"我\"",
    "每一步结果正确；且/或切换生效；相对日期和\"我\"都可用",
    "§8 高级筛选", "增强")
add(M, "单元格编辑", "P0", "无",
    "1. 在单元格里分别改文本、下拉、日期、金额、勾选\n2. 刷新页面",
    "保存成功，刷新后仍是新值",
    "§8 在单元格里直接改值", "同等")
add(M, "同时编辑冲突", "P1", "两个浏览器（或一个普通 + 一个无痕窗口）登录两个用户，打开同一看板",
    "1. 两边同时开始编辑同一行同一个单元格\n2. A 先保存\n3. B 再保存",
    "B 收到\"别人已经改过\"的提示，A 的值没有被悄悄覆盖",
    "老系统没有冲突检测", "增强")
add(M, "实时刷新", "P1", "同上",
    "1. A 改一个状态\n2. 观察 B 的屏幕（不刷新）",
    "B 的看板几秒内自动显示新状态",
    "老系统没有", "新增")
add(M, "保存个人视图", "P0", "无",
    "1. 调好列、筛选、排序\n2. Views → 保存为 Personal\n3. 刷新后从 Views 选它",
    "视图还原列、筛选、排序；其他用户看不到",
    "§8 Saved View：Personal", "同等")
add(M, "共享视图", "P0", "manager 或管理员",
    "1. 保存为 Shared\n2. 换一个用户登录查看 Views",
    "其他用户能看到并使用，但不能修改（除非有权限）",
    "§8 Saved View：Shared", "同等")
add(M, "默认视图", "P1", "已有共享视图",
    "1. 把一个视图设为这块看板的默认\n2. 另一个用户打开这块看板",
    "自动套用默认视图",
    "§8 标成这块看板的默认视图", "同等")
add(M, "批量改字段", "P0", "勾选 3 行",
    "1. 批量栏 → Edit field → 选 Status → 设为 Hold",
    "3 行都改成 Hold",
    "§8 勾选多行批量改同一字段", "同等")
add(M, "批量改软件", "P0", "勾选 3 行（软件各不相同）",
    "1. Edit field → Software → 分别试 Add、Remove、Replace",
    "Add 只加不删；Remove 只去掉选中的；Replace 全部替换",
    "§8 批量改软件", "增强")
add(M, "批量改某角色的人", "P0", "勾选 3 行",
    "1. Edit field → Preparer → 选一个人",
    "3 行的 Preparer 都变成这个人，其他角色不变",
    "§8 批量改某一个角色上的人", "同等")
add(M, "导出 CSV", "P0", "看板上有数据，并设了筛选",
    "1. 看板右上角菜单 → Export CSV\n2. 用 Excel 打开",
    "文件能下载；中文不乱码；列与当前显示一致",
    "§8 从看板菜单导出 CSV", "同等")
add(M, "移动到另一块看板", "P1", "勾选 1 行",
    "1. 批量栏 → Move → 选另一块看板",
    "该行从当前看板消失，出现在目标看板",
    "§8 改 project_type 换看板", "同等")

# ---------------- 新建项目 ----------------
M = "新建项目"
add(M, "Accounting 必填项", "P0", "打开一块会计看板",
    "1. 点 New\n2. 不填客户、公司、财年直接保存\n3. 补齐后保存",
    "缺项时提示哪些必填；补齐后创建成功，出现在当前看板",
    "§16 会计必填：项目名称、客户、公司、财年、项目类型", "同等")
add(M, "从客户带出年结和合伙人", "P0", "客户有主实体（年结 June）和负责合伙人",
    "1. 新建项目只选这个客户，不填 Year End 和 Partner\n2. 保存后看这一行",
    "Entity 自动是主实体；Year End = June；团队里自动有该合伙人（Partner），分配日期为今天",
    "§16 年结从实体带入；没有 Partner 时用客户合伙人补一行", "同等")
add(M, "手填年结不被覆盖", "P1", "同上",
    "1. 新建时手动选 Year End = March",
    "保存后仍是 March",
    "§16 年结只在为空时带入", "同等")
add(M, "默认状态", "P1", "无",
    "1. 新建项目不选状态",
    "状态为 Not started",
    "§16 状态不合法时用 Not started", "同等")
add(M, "Grants 必填项和默认值", "P0", "打开 FY 2026",
    "1. 点 New，看哪些必填、Company 默认是什么\n2. 填客户后保存",
    "按老系统：必填项目名称、客户、公司；公司默认 Top Grants。如果新系统不要求公司或没有默认值，请记为问题",
    "§16 Grants 必填名称、客户、公司；公司默认 Top Grants，频率默认 One-off", "待确认")
add(M, "项目名称重复", "P1", "看板上已有项目 \"Test Client A - ITR 2026\"",
    "1. 再新建一个同名项目",
    "按老系统应被拒绝。新系统目前可能允许同名（导入时同一客户多行需要），请记录实际行为，我们再决定",
    "§16 project_name 已存在则失败", "待确认")
add(M, "客户名有歧义", "P2", "有两个相似名称的客户",
    "1. 新建项目时在客户框里搜索",
    "能看到两个，必须明确选一个，不会自动猜",
    "§16 客户显示名匹配多个时失败", "同等")

# ---------------- Roll over ----------------
M = "Roll over"
add(M, "会计 Roll over 到同一看板", "P0", "勾选 2 行 FY 2025-2026 的会计项目",
    "1. 批量栏 → Roll over\n2. 目标看板保持当前，财年选 +1\n3. 确认",
    "生成 2 个新项目，财年为 2026-2027，名称按规则改了后缀，状态 Not started；原项目保持不变",
    "§16 会计默认留在当前看板；财年默认加一年", "同等")
add(M, "逐列选择带走/清空/设值/+1 年", "P0", "同上",
    "1. Roll over 弹窗里：Notes 选 Clear，Priority 选 Copy，Target Month 选 Set=March，Reset Date 选 +1 year\n2. 确认",
    "新项目：Notes 为空；Priority 与原来相同；Target Month = March；Reset Date 比原来晚一年；Monthly Status 默认清空",
    "§16 每列可带走、清空、设新值；日期列可加一年", "同等")
add(M, "固定处理的字段", "P1", "同上",
    "1. 查看新项目的 Client、Company",
    "Client 和 Company 总是带走，不出现在可选列表里",
    "§16 customer、company 原值抄过去", "同等")
add(M, "命名规则", "P1", "原项目名 \"Test Client A - ITR 2025-2026\"",
    "1. Roll over 不填后缀，财年 +1\n2. 再对同一原项目 Roll over 一次（同一目标）",
    "第一次去掉旧财年加新财年；第二次名称冲突时自动加 (2)",
    "§16 去掉旧后缀再加新后缀；冲突时括号从 2 递增", "同等")
add(M, "团队和软件", "P1", "原项目有 Preparer 和 Software",
    "1. Roll over 时团队选 Copy、软件选 Clear",
    "新项目团队人员相同，分配日期是今天；软件为空",
    "§16 团队和软件只在选择带走时复制；分配日期改为当天", "同等")
add(M, "归档原项目", "P0", "勾选 1 行",
    "1. Roll over 时勾选\"归档原项目\"",
    "生成新项目；原项目进入 Archived，来源显示 Archived by hand；不触发自动化",
    "§16 勾选归档原项目：来源 Manual，不跑自动化", "同等")
add(M, "Grants 滚到下一年", "P0", "FY 2026 看板勾选 2 行",
    "1. Roll over，不改目标",
    "默认目标是 FY 2027；新项目状态 Not started；三个日期、Application Progress、Rebate Amount 默认清空",
    "§16 Grants 默认下一年的财年看板，状态重置", "同等")
add(M, "Grants 留在同一看板", "P2", "同上",
    "1. Roll over 时把目标改成 FY 2026",
    "副本生成在 FY 2026",
    "§8 也可以留在同一块看板", "同等")

# ---------------- 归档、恢复、删除 ----------------
M = "归档、恢复与删除"
add(M, "手动归档项目", "P0", "勾选 2 行",
    "1. 批量栏 → Archive → 确认\n2. 打开侧边栏 Archived",
    "2 行从看板消失，出现在 Archived，来源 Archived by hand",
    "§16 归档项目：来源 Manual，这条保存会跑自动化", "同等")
add(M, "恢复项目", "P0", "Archived 里有项目",
    "1. 在 Archived 勾选并恢复",
    "回到原看板，从 Archived 消失",
    "§16 恢复项目", "同等")
add(M, "原看板已归档时恢复", "P1", "某项目被手动归档后，它原来的看板也被归档了",
    "1. 在 Archived 恢复这个项目",
    "系统要求先选一块现存看板，选了才恢复；取消则不恢复",
    "§16 Archived (Holding) 的项目恢复前要另选看板", "同等")
add(M, "归档看板", "P1", "管理员；新建一块测试看板，放 3 行",
    "1. 看板菜单 → Archive board\n2. 去 Workspace setup → Boards 恢复它",
    "归档后看板从侧边栏消失，3 行一起归档；恢复后看板和这 3 行原样回来",
    "§16 删除看板：项目挪到 Archived (Holding)，来源 Type Deleted", "增强")
add(M, "删除项目连同任务", "P0", "manager 或管理员；项目下有任务和子任务",
    "1. 勾选该项目 → Delete → 确认\n2. 管理员进 Activity 找到这次删除并恢复",
    "项目和任务都消失；确认框说明会一起删除；恢复后项目和任务都回来",
    "§16 删除项目连同任务，不能撤销", "增强")

# ---------------- 任务 ----------------
M = "任务"
add(M, "查看项目任务", "P0", "项目已有任务",
    "1. 点项目行打开详情 → Tasks",
    "列出该项目的任务",
    "§9 在项目行上展开看任务", "同等")
add(M, "新建任务", "P0", "无",
    "1. Tasks 里新建一条，填标题、状态、优先级、截止日",
    "保存成功",
    "§9 给一个项目新建任务", "同等")
add(M, "批量建任务", "P0", "看板上勾选 3 行",
    "1. 批量栏 → Add task → 填标题",
    "3 个项目各多一条同名任务",
    "§9 给选中的多个项目各建一条任务", "同等")
add(M, "子任务", "P1", "已有任务",
    "1. 在任务下加子任务",
    "子任务挂在父任务下显示",
    "§9 parent_task", "同等")
add(M, "任务状态选项", "P1", "无",
    "1. 查看任务 Status 下拉",
    "Not started yet、Working on it、Stuck、Done；新建默认 Not started yet",
    "§9 Task 状态 4 个，默认 Not started yet", "同等")
add(M, "任务人员", "P1", "已有任务",
    "1. 给任务加人并选角色",
    "保存成功，角色选项与项目团队相同",
    "§9 custom_task_members", "同等")
add(M, "任务财年和期间", "P2", "已有任务",
    "1. 给任务设财年和期间文字（如 Q1）",
    "保存成功",
    "§9 custom_fiscal_year、custom_period", "待确认")
add(M, "删除任务含子任务", "P1", "任务下有子任务",
    "1. 删除父任务",
    "父任务和子任务一起删除",
    "§9 删除任务，可选连同子任务", "同等")

# ---------------- 状态与看板设置 ----------------
M = "看板设置与配置"
add(M, "看板只启用部分状态", "P0", "管理员",
    "1. 看板菜单 → Board settings → 只勾选 5 个状态\n2. 点该看板某行 Status",
    "下拉只显示这 5 个",
    "§10 每块看板只启用状态池的一部分", "同等")
add(M, "看板只显示部分字段", "P2", "管理员",
    "1. Board settings 里限定字段",
    "该看板只能选这些列",
    "老系统没有", "新增")
add(M, "调整看板顺序", "P1", "管理员",
    "1. Workspace setup → Boards，拖动顺序",
    "侧边栏顺序跟着变",
    "§10 调整看板在侧边栏的顺序", "同等")
add(M, "新建看板", "P0", "管理员",
    "1. 侧边栏 New board，填名称",
    "新看板出现在侧边栏，可以建项目",
    "§4 管理员可以新建 Project Type", "同等")
add(M, "维护状态池", "P1", "管理员",
    "1. Workspace setup → Statuses，新增一个状态，设颜色和类别\n2. 改一个状态的名称",
    "看板下拉里出现新状态；改名后已有项目显示新名称",
    "§10 状态池由 Property Setter 改", "增强")
add(M, "新增字段（零代码）", "P1", "管理员",
    "1. Workspace setup → Fields，新增一个 Select 字段\n2. 回看板",
    "新列可用，可编辑、筛选、排序",
    "老系统加字段要改代码", "新增")
add(M, "维护团队角色", "P2", "管理员",
    "1. Workspace setup → Team roles，新增一个角色",
    "项目团队里可以选这个角色",
    "§6 角色是固定选项", "增强")
add(M, "维护软件、公司名单", "P1", "管理员",
    "1. Settings 里的主数据：新增软件，停用一个旧软件，给 QuickBooks 加别名",
    "新软件可选；停用的不再出现在新选项里但旧数据保留",
    "§6 Software 是可维护的名单", "同等")

# ---------------- 自动化 ----------------
M = "自动化"
add(M, "规则列表和搜索", "P0", "manager 或管理员",
    "1. Automations 页面\n2. 按名字搜索",
    "只列出当前产品线的规则；搜索可用",
    "§11 按当前模块列出规则、按名字搜索", "同等")
add(M, "新建、启用、停用、删除", "P0", "同上",
    "1. 新建一条规则并保存\n2. 停用 → 启用 → 删除",
    "每一步都生效；停用时不再触发",
    "§11 新建、修改、启用、停用、删除", "同等")
add(M, "状态变成 → 改状态/通知", "P0", "规则：Status 变成 Ready for manager review 时，通知 Manager",
    "1. 把某行状态改成 Ready for manager review\n2. 用该行 Manager 的账号看右上角铃铛",
    "Manager 收到通知；Automation logs 有一条成功记录",
    "§11 Status changes to + Notify someone", "同等")
add(M, "附加条件（状态是/看板是）", "P1", "规则：Status 变成 X，且条件里加\"看板是 BAS\"",
    "1. 在 BAS 和 ITR 各改一行状态为 X",
    "只有 BAS 那行触发",
    "§11 Status is、Project type is 作为附加条件", "同等")
add(M, "日期到了 → 按频率推 Lodgement Due", "P0", "规则：Lodgement Due 到了（当天或之后）→ Push a date forward：Lodgement Due 按频率；一行 Frequency=Quarterly、Lodgement Due=今天",
    "1. 让日期任务跑一次（管理员在服务器执行：python -m app.cli run-job automations.date_rules；或等整点）\n2. 看这一行",
    "Lodgement Due 往后推 3 个月；Automation logs 记录了前后值",
    "§11 Date reaches + Roll Lodgement Due forward by frequency；每小时跑一次", "同等")
add(M, "按固定间隔推日期", "P1", "同上类规则，改为推 1 周 / 2 周 / 1 月 / 1 季 / 1 年，也试 Target Month",
    "1. 逐个试",
    "推的长度正确；月份字段 12 月往后推会回到 1 月",
    "§11 Push a date：频率、一周、两周、一月、一季、一年", "同等")
add(M, "日期到了 → 重置状态", "P1", "规则：Reset Date 到了 → 状态设为 Not started",
    "1. 一行 Reset Date=今天，跑日期任务",
    "状态变成 Not started",
    "§11 Reset status to", "同等")
add(M, "自动归档", "P1", "规则：状态变成 Completed → Archive the item",
    "1. 把一行改成 Completed",
    "该行进入 Archived，来源显示 Archived by automation",
    "§11 Archive project；来源 Automation", "同等")
add(M, "Grants 日期临近 → 高亮", "P0", "规则：Portal Access Expiry 提前 1 个月 → Highlight row 红色；客户的 Portal Access Expiry = 今天 + 1 个月",
    "1. 跑日期任务\n2. 打开 Grants 看板",
    "那一行显示红色高亮；Automation logs 有记录",
    "§11 Date is approaching（提前月/周/天）+ Highlight row", "同等")
add(M, "日期到了 → 清除高亮", "P1", "规则：某日期到了 → Clear row highlight",
    "1. 对已高亮的一行触发",
    "高亮消失",
    "§11 Clear highlight", "同等")
add(M, "同一日期只触发一次", "P1", "已触发过的日期规则",
    "1. 再跑一次日期任务",
    "同一行同一日期不会重复执行（不会再推一次日期）",
    "隐含要求：不能重复触发", "同等")
add(M, "预览命中哪些行", "P2", "编辑规则时",
    "1. 点预览",
    "列出当前会命中的项目",
    "老系统没有", "新增")
add(M, "运行日志", "P0", "已有若干次运行",
    "1. 打开 Automation logs",
    "每次运行显示：规则、项目、时间、来源、成功/失败、改了哪些字段（前值→后值）；失败显示原因",
    "§11 Automation Run Log 和 Change 子表", "同等")
add(M, "撤销一次运行", "P1", "已有一次改过字段的运行",
    "1. 在 Automation logs 点 Undo",
    "被改的字段恢复原值",
    "老系统没有", "新增")
add(M, "新建时触发、自动建任务", "P2", "规则：Item is created → Create a task",
    "1. 新建一个项目",
    "该项目自动多一条任务",
    "老系统没有", "新增")

# ---------------- 通知与 Updates ----------------
M = "通知与 Updates"
add(M, "新增/编辑/删除 Update", "P0", "打开项目详情",
    "1. Updates 里写一条\n2. 编辑它\n3. 删除它",
    "三步都成功；显示作者和时间",
    "§12 Updates 新增、修改、删除", "同等")
add(M, "@ 提及", "P0", "两个用户 A、B",
    "1. A 在 Update 里输入 @ 并选 B，发送\n2. B 登录看铃铛",
    "B 收到通知，点通知能跳到该项目",
    "§12 @ 人，被 @ 的人收到通知", "同等")
add(M, "通知已读", "P1", "有未读通知",
    "1. 打开铃铛，标为已读",
    "未读数减少",
    "§11 Notification Log", "同等")
add(M, "邮件通知", "P2", "无",
    "1. 无",
    "新系统暂只有站内通知，邮件等邮件模块（已知限制），记录即可",
    "§11 是否发邮件取决于通知邮件开关", "差异")

# ---------------- 活动记录与撤销 ----------------
M = "活动记录与撤销"
add(M, "项目活动记录", "P0", "改过某项目的几个字段",
    "1. 打开项目详情 → Activity",
    "按时间列出每次修改：谁、什么时候、哪个字段、前值、后值",
    "§12 打开一个项目的活动记录", "同等")
add(M, "全局活动筛选", "P0", "有多个用户做过修改",
    "1. 侧边栏 Activity\n2. 分别按人、按对象（项目/客户）、按动作（创建/更新/删除）筛选",
    "筛选结果正确",
    "§12 全局活动按人、对象、动作筛选", "同等")
add(M, "修改值的可见性", "P1", "member 用户 B 和 manager",
    "1. 分别用 B 和 manager 打开 Activity",
    "manager 能看到具体前后值；B 看不到值（只看到改了哪个字段）",
    "§12 值默认遮住，输入密码后显示", "差异")
add(M, "撤销一条修改", "P0", "刚改过某项目 Status",
    "1. Activity 里对这条点 Undo",
    "Status 回到原值；这次撤销本身也被记录",
    "§16 撤销项目修改", "同等")
add(M, "已被再改过时拒绝撤销", "P0", "某字段先由 A→B，再由 B→C",
    "1. 撤销 A→B 那一条",
    "被拒绝，不会把 C 覆盖成 A",
    "§16 当前值必须仍等于当时改成的值，否则拒绝", "同等")
add(M, "按批次撤销", "P0", "做过一次批量改字段（3 行）",
    "1. Activity 里对这次批量操作点 Undo whole batch",
    "3 行一起恢复；其中被别人再改过的行跳过，其余照常恢复",
    "§16 批量撤销按批次处理，不能撤销的行跳过", "同等")
add(M, "撤销不触发自动化", "P1", "有一条\"状态变成 X\"的规则",
    "1. 把状态改成 X（触发一次）\n2. 撤销后再撤销撤销（或制造一次撤销回 X）",
    "撤销写回旧值时不触发规则",
    "§16 写回旧值时不跑自动化", "同等")
add(M, "客户、任务、联系人的撤销", "P2", "改过客户名称、任务标题",
    "1. 在 Activity 里撤销这些修改",
    "都能撤销",
    "老系统只能撤销项目字段", "增强")

# ---------------- 用户与个人设置 ----------------
M = "用户与个人设置"
add(M, "搜索用户", "P1", "管理员",
    "1. Users 页面搜索",
    "能按名字或邮箱找到",
    "§13 搜索用户", "同等")
add(M, "新建用户", "P0", "管理员",
    "1. Users → New，填姓名、邮箱，给 Accounting member、Grants viewer\n2. 设密码\n3. 用新账号登录",
    "能登录，权限符合所给角色；不会自动发欢迎邮件",
    "§13 新建用户：姓名、邮箱、是否启用、能否进 Accounting/Grants", "增强")
add(M, "修改用户和停用", "P0", "管理员；用户 D 已登录",
    "1. 改 D 的姓名和角色\n2. 停用 D",
    "修改生效；停用后 D 不能再登录",
    "§13 修改资料、是否启用", "同等")
add(M, "别名", "P1", "管理员",
    "1. 给用户填 Other names（如 CL）\n2. 在 Update 里 @CL，或导入含 CL 的 CSV",
    "能用别名找到这个人",
    "老系统没有", "新增")
add(M, "我的资料", "P0", "任意用户",
    "1. 左下角名字 → Settings → 改显示名",
    "保存后左下角名字更新",
    "§13 Settings：My Profile", "同等")
add(M, "修改密码", "P0", "任意用户",
    "1. Settings → 改密码（需输入旧密码）\n2. 退出后用新密码登录",
    "旧密码错误时不能改；改后新密码可用、旧密码不可用",
    "§13 Settings：Change Password", "同等")

# ---------------- 系统维护 ----------------
M = "系统维护"
add(M, "System health", "P1", "管理员",
    "1. 打开 System health",
    "显示部署版本、数据库版本、后台进程（worker）在运行、失败的任务（如有）",
    "§4 Debug Tools", "增强")
add(M, "重试失败任务", "P2", "System health 里有失败的投递（如没有可跳过）",
    "1. 点 Retry",
    "重新执行，成功后从失败列表消失",
    "老系统没有", "新增")
add(M, "健康检查地址", "P2", "无",
    "1. 浏览器打开 /api/health",
    "返回 git_sha 和 db_revision，与刚部署的版本一致",
    "老系统没有", "新增")

# ---------------- 数据迁移 ----------------
M = "数据迁移"
add(M, "上传 CSV 与编码识别", "P0", "管理员；先按 MIGRATION.md 建好用户和别名",
    "1. Data migration → 选目标看板 Financials & Tax Return\n2. 上传老系统导出的 CSV（Excel 另存的 GBK 文件）",
    "页面显示识别到的编码，预览里中文不乱码",
    "迁移是新系统功能；老系统数据必须能完整搬过来", "新增")
add(M, "列映射", "P0", "接上一条",
    "1. 检查自动匹配的列\n2. 把 Last Updated 设为 Don't import",
    "老系统列名大多自动对上；可以手动改",
    "同上", "新增")
add(M, "值匹配", "P0", "接上一条",
    "1. 查看没对上的状态、选项、人名\n2. 指向已有值或新建",
    "只列出没对上的值；处理后进入下一步",
    "同上", "新增")
add(M, "Check 与 Import", "P0", "接上一条",
    "1. 点 Check，看 Ready / With warnings / With errors\n2. Import",
    "有 error 的行不导入；完成后报告各结果行数，并有逐列对账（源文件有值的行数 vs 导入后有值的行数）",
    "同上", "新增")
add(M, "重复导入不重复创建", "P0", "已导入一次",
    "1. 用同一文件再导入一次",
    "结果是 updated，不是 created；看板行数不变",
    "同上", "新增")
add(M, "Grants 导入", "P0", "Grants 的 CSV 导出",
    "1. 导入到 FY 2026",
    "日期（20260911、2026/9/11 等）都解析成正确日期；人名匹配到用户；客户级字段写到客户上",
    "同上", "新增")
add(M, "回滚整批导入", "P0", "已有一次导入",
    "1. Roll back this import",
    "这次导入创建的项目全部撤掉，更新过的恢复原值",
    "同上", "新增")
