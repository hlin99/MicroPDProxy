1. 这个文件是最核心的功能文件 https://github.com/hlin99/MicroPDProxy/blob/main/core/MicroPDProxyServer.py
	使用方法
		a. Adjust proxy server, xpyd_start_proxy.sh
			# Adjust Prefill/Decode IPs
			PREFILL_IPS=("10.239.129.9" "10.239.129.67" "10.239.129.21" "10.239.128.165" "10.239.128.244" "10.239.128.153")
			DECODE_IPS=("10.239.129.81" "10.239.129.165" "10.239.129.67" "10.239.129.21")
		b. bash xpyd_start_proxy.sh x y z
			# note: x for prefill nodes number, y for decode nodes number, z 是TP size （每个node是8个world size）

2. 这个文件里面的内容已经在真正的硬件平台上得到了验证。代码是没有大问题的。 所以交给你的第一个任务是，在不做core改动的情况下，调试dummy_nodes，让dummy_nodes在下列proxy server的配置下都能正常工作
	a. bash xpyd_start_proxy.sh 1 2 1
	b. bash xpyd_start_proxy.sh 2 2 1
	c. bash xpyd_start_proxy.sh 1 2 2
	d. bash xpyd_start_proxy.sh 1 2 4
	e. bash xpyd_start_proxy.sh 1 2 8
	f. bash xpyd_start_proxy.sh 2 2 2
	g. bash xpyd_start_proxy.sh 2 4 1
	h. bash xpyd_start_proxy.sh 2 4 2

调试好了提交PR

3. 任务二（进行中）
	目标
	修改 core/xpyd_start_proxy.sh，将当前固定参数形式改为命令行参数驱动的形式。

	脚本需要支持以下参数：

	Prefill 参数
	--prefill-nodes / -pn
	--prefill-tp-size / -pt
	--prefill-dp-size / -pd
	--prefill-world-size-per-node / -pw

	Decode 参数
	--decode-nodes / -dn
	--decode-tp-size / -dt
	--decode-dp-size / -dd
	--decode-world-size-per-node / -dw

	可选参数
	--prefill-base-port
	--decode-base-port

	参数化目标
	将脚本从固定配置改为类似下面的调用形式：

	.sh \
	  --prefill-nodes $a \
	  --prefill-tp-size $b \
	  --prefill-dp-size $c \
	  --prefill-world-size-per-node $d \
	  --decode-nodes $e \
	  --decode-tp-size $f \
	  --decode-dp-size $g \
	  --decode-world-size-per-node $h

	由于命令较长，允许同时提供短参数别名（如 -pn、-pt 等）。

	校验规则
	1. 所有参数必须为正整数
	2. tp_size、dp_size 必须是 2 的 n 次幂
	3. 必须满足：
	   tp_size * dp_size == nodes * world_size_per_node
	4. nodes 数量不能超过对应 IP 列表长度：
	   nodes <= IP 列表长度

	拓扑与映射规则

	1. 基本定义
	- 一个 instance = 一个 TP group
	- N 个 TP shard 组成一个 instance
	- instance 数量 = dp_size
	- tp_size 决定一个 instance 内有多少 TP shard
	- dp_size 决定总共有多少个 instance

	2. Node / IP / Port 规则
	- 每个 node 对应一个 IP
	- 同一个 node 上可以承载多个 instance
	- 同一个 node 上的不同 instance：
	  - IP 相同
	  - port 不同
	  - port 按 +1 递增

	3. Instance 对 proxy 的暴露规则
	- 一个 instance 对 proxy 只暴露一个 IP:PORT
	- 即使该 instance 内部跨多个 node，也只使用该 instance 主节点（例如 rank0 所在 node）的 IP 和该 instance 的 port 作为对外 endpoint
	- 主节点定义为：该 instance 的 rank0 所在 node，也等价于该 TP group 分配到的第一个 node

	不同 TP / world size 场景下的映射规则

	情况一：tp_size <= world_size_per_node
	表示一个 node 足以容纳一个或多个完整 TP group。

	规则：
	- 每个 node 可承载：
	  world_size_per_node / tp_size
	  个 instance
	- 同一 node 上多个 instance 使用相同 IP、不同 port
	- port 递增分配

	情况二：tp_size > world_size_per_node
	表示一个 instance 的 TP group 需要跨多个 node 才能组成。

	规则：
	- 每个 instance 跨：
	  tp_size / world_size_per_node
	  个 node
	- 同一个 instance 的不同 node shard 使用相同 port
	- 对 proxy 暴露时，只暴露主节点的 IP:PORT

	实现约束
	- 只修改 core/xpyd_start_proxy.sh
	- 其他 core 业务逻辑文件不动
	- 如有必要，可做少量非业务逻辑性质的修正（如路径、参数解析辅助）
