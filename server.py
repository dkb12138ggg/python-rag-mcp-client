from mcp.server.fastmcp import FastMCP  


mcp = FastMCP()

@mcp.tool()
def add(a: int, b: int):
  """
  计算两个整数的和
  """
  return a + b

@mcp.tool()
def subtract(a: int, b: int):
  """
  计算两个整数的差
  """
  return a - b

@mcp.tool()
def multiply(a: int, b: int):
  """
  计算两个整数的乘积
  """
  return a * b

if __name__ == "__main__":
    # 以 stdio 方式运行服务器
    mcp.run()

