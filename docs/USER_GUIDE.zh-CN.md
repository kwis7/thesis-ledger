# 使用指南

[English](USER_GUIDE.md) · [README](../README.zh-CN.md)

先用离线案例看懂研究流程，再接入公开数据监测。界面目前使用英文，本指南直接引用页面上的按钮名称。

## 打开第一个工作区

下载并解压仓库，或用 Git 克隆。在包含 `run.py` 的文件夹打开终端。安装好 Python 3.10 或更新版本后，运行：

```sh
python3 run.py case EXE
```

如果浏览器没有自动打开，访问 `http://127.0.0.1:8765/#lab`。使用工作台时，这个终端进程需要保持运行。案例已经自带历史数据，不需要请求 SEC、调用外部模型或发送邮件。

资料保存在 `.thesisledger/exe-case/`。按 Ctrl+C 停止，之后运行同一条命令就能接着使用。想另外开一份案例，或避开已占用的端口，可以运行：

```sh
python3 run.py case EXE --workspace .thesisledger/exe-second --port 8766
```

监测命令必须使用对应案例的同一个工作区。默认监测 `.thesisledger/exe-case`；如果案例放在别处，记得把相同路径传给 `--workspace`。

## 跑完一次研究流程

1. 进入 **Research Lab**，查看财报数据的来源和财务期间。
2. 把 **Realized price** 从 3.5 调到 4.0 USD/Mcfe，顺着现金流传导查看变化。这是情景推演，不会替换已接受的模型。
3. 点击 **Run evidence review**，查看三条复核建议、引用和实际工具结果。默认流程离线运行，使用确定性的复核计划。
4. 点击 **Verify saved run**，重跑保存的工具决策并比较哈希。较早的记录需要对应代码版本才能重现。

打开来源或点击 **Mark reviewed**，只是记录你看过这条提醒。接受新的经营假设或完整财务基线是另一项明确操作，会留下模型版本。新财报提醒本身不会更新财务模型。

## 先接上 EXE 官网监测

保持案例工作台运行，在仓库目录另开一个终端，执行：

```sh
python3 run.py ir-watch EXE --workspace .thesisledger/exe-case --once
```

程序先检查网站的 robots 规则，再读取 EXE 官方财报列表。进入 **Monitor & Timeline** 或 **Alerts**，点击 **Refresh saved workspace** 查看结果。页面会显示官网状态、最后检查时间，以及新生成的复核提醒。已经发现过的公告可能返回零条新提醒，这是正常结果。

这条链路目前只适配 EXE，识别公告日期、类型、申报编号和报告链接。报告对应哪个财务期间、有哪些新数字，仍需要打开文件核对，再决定是否提出模型更新。官网检查成功，不会清除 SEC 的独立故障状态，也不会把旧财务数据标记为最新。

<a id="sec-setup"></a>

## 向 SEC 声明应用身份

SEC 的 `data.sec.gov` 公开数据 API 不需要登录或 API key。自动程序需要在 HTTP `User-Agent` 请求头里说明应用身份和联系方式。这里没有上传证件、注册开发者账户或获取“实名认证通过”证书的步骤。[官方 API 说明](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)和[自动访问说明](https://www.sec.gov/about/webmaster-frequently-asked-questions)分别解释了这两件事。

### 第一步：准备真实信息

填写应用名称与版本、实际运行者或机构名称，以及你能够接收邮件、愿意作为项目联系方式发送给 SEC 的邮箱。可以使用项目专用邮箱，保持可联系即可。不要把密码、API key、账户号或证件资料放进请求头。

下面是**填写模板，不能原样复制运行**。把 `<YOUR_REAL_OPERATOR_NAME>` 和 `<YOUR_REAL_CONTACT_EMAIL>` 都换成自己的真实信息，去掉尖括号，保留外层的一对引号。

```sh
python3 run.py sec-watch EXE --workspace .thesisledger/exe-case --user-agent 'ThesisLedger/0.2.2 <YOUR_REAL_OPERATOR_NAME> <YOUR_REAL_CONTACT_EMAIL>' --once
```

邮箱会作为请求头发送给 SEC，不需要写进公开仓库。终端历史和本地进程列表可能保留命令，所以请选择你愿意用于这个用途的联系方式。

ThesisLedger 会把这段文字传给请求头，不会将它保存在网页快照或工作区状态中。程序只检查参数是否能用于请求，不会验证邮箱归属，也不会替你向 SEC 注册。正确声明身份仍不保证每个网络环境都能访问。

### 第二步：先检查一次

替换好信息后，先保留 `--once` 运行。程序只请求一次 EXE 的公告元数据。进入 **Monitor & Timeline**，刷新页面，查看 **SEC direct**、最后检查时间和结果。

| 结果 | 怎样理解和处理 |
| --- | --- |
| `processed` | 有新的本地复核提醒，打开来源检查；财务数字仍需要另行核对 |
| `unchanged` | 最新符合条件的公告已经知道，或没有推进案例；零条新提醒是正常结果 |
| `paused` | 先在工作台恢复监测，再主动检查一次 |
| `data_gap` | 限定范围内没有找到可用的定期报告，先查看来源缺口 |
| HTTP 403 / `Undeclared Automated Tool` | 停下来检查身份声明和访问说明，错误页不能当作财报 |
| 网络或超时错误 | 这次没有获得可验证结果，要与服务器明确返回的 HTTP 拒绝分开处理 |

检查成功说明这次取得了合格的公告元数据，并不代表 SEC 对你的身份、应用或财务模型作了认证。

### 第三步：仍然被拒绝时

先确认模板已经替换、整段声明放在引号内、联系邮箱可用。解决了具体配置问题后，再主动执行一次检查。不要反复重试、轮换身份或代理。

如果仍然出现 Access Denied，[SEC 的 FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions)提供了 `webmaster@sec.gov` 联系方式，并要求附上错误信息与公网 IP。如果你决定联系，先自行检查准备发送的内容。ThesisLedger 不会替你发邮件、查找公网 IP 或上传诊断材料。

SEC 访问没有解决时，仍可以使用离线案例，或主动选择 `ir-watch EXE`。两路来源状态会分别保留。目前项目已实测官网链路成功一次；SEC 直连恢复及持续可用性仍未验证，详情见[验证记录](VERIFICATION.md)。

## 持续监测与暂停

单次检查成功后，可以去掉相应命令的 `--once`，让终端进程每 15 分钟检查一次。使用 `sec-watch` 时保留已经填写好的身份声明。这不会自动安装系统定时任务。

官网链路的持续运行命令是：

```sh
python3 run.py ir-watch EXE --workspace .thesisledger/exe-case
```

在 **Monitor & Timeline** 点击 **Pause monitoring**，可以停止开始下一轮采集。已经开始的一轮检查可能仍会完成，包括这一轮剩余的请求；暂停不会取消这轮检查。正常运行的监测进程会等待你恢复。采集失败后，进程会退出，并留下本地故障提醒；解决问题后需要重新启动命令，页面里的 Resume 不能启动已经退出的终端进程。

同一份已验证公告在两路来源之间也会去重，同一次持续故障不会反复提醒。点击刷新时，只要已接受的研究基线没变，沙盒参数和当前研究记录都会保留。提醒进入本地收件箱，邮件预览不会发送消息。

<a id="own-research"></a>

## 导入自己的研究

按[输入约定](DATA_CONTRACT.md)准备公开或明确脱敏的公司 JSON 文件，注明来源日期、单位、假设和缺口。下面的 `my-company.json` 指你准备好的文件，并不是项目已经提供的样例。使用新的工作区，前后保持同一路径：

```sh
python3 run.py init --workspace .thesisledger/my-research
python3 run.py import my-company.json --workspace .thesisledger/my-research
python3 run.py serve --workspace .thesisledger/my-research --port 8766
```

import 用来添加公司，不能覆盖已经存在的公司。完整更新可以通过 `baseline FILE --workspace PATH` 提出候选，再到工作台检查并明确接受。新公告提醒只含元数据，还不是可以直接接受的财务文件。

[Agent 指南](../agents/START_HERE.md)提供了一段开场请求，可以请 Agent 帮你整理输入。内置模型支持工业、经常性客户收入和有限范围的商品生产商业务，不会自动为任意 ticker 生成完整模型。新的公司官网监测也需要另外适配。

想练习证据冲突与来源故障，可以看[虚构公司演示](QUICKSTART.md)。[Agent 运行说明](AGENT_RUNTIME.md)介绍可选的真实模型调用，[自托管说明](SELF_HOSTING.md)介绍私有云配置和邮件功能。这些路线有各自的配置与验证边界，本地案例不需要它们。
