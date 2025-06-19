#!/usr/bin/env python3
"""生产环境测试脚本"""

import asyncio
import json
import time
from typing import Dict, Any

import httpx


async def test_api_endpoints():
    """测试API端点"""
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        print("🧪 开始API测试...")
        
        # 测试根端点
        print("📍 测试根端点...")
        response = await client.get(f"{base_url}/")
        print(f"   状态码: {response.status_code}")
        print(f"   响应: {response.json()}")
        
        # 测试健康检查
        print("\n🏥 测试健康检查...")
        response = await client.get(f"{base_url}/health")
        print(f"   状态码: {response.status_code}")
        health_data = response.json()
        print(f"   整体状态: {health_data.get('status', 'unknown')}")
        
        # 测试工具列表
        print("\n🔧 测试工具列表...")
        response = await client.get(f"{base_url}/tools")
        print(f"   状态码: {response.status_code}")
        if response.status_code == 200:
            tools_data = response.json()
            print(f"   工具数量: {tools_data.get('count', 0)}")
            if tools_data.get('tools'):
                for tool in tools_data['tools'][:3]:  # 显示前3个工具
                    print(f"   - {tool.get('function', {}).get('name', 'unknown')}")
        
        # 测试服务器状态
        print("\n📊 测试服务器状态...")
        response = await client.get(f"{base_url}/status")
        print(f"   状态码: {response.status_code}")
        if response.status_code == 200:
            status_data = response.json()
            print(f"   服务器数量: {len(status_data.get('servers', []))}")
            print(f"   并发请求: {status_data.get('concurrent_requests', 0)}")
        
        # 测试查询功能
        print("\n💬 测试查询功能...")
        query_data = {
            "query": "计算 10 + 15",
            "user_id": "test_user"
        }
        response = await client.post(f"{base_url}/query", json=query_data)
        print(f"   状态码: {response.status_code}")
        if response.status_code == 200:
            query_result = response.json()
            print(f"   响应内容: {query_result.get('content', '')[:100]}...")
            print(f"   使用工具数: {len(query_result.get('tools_used', []))}")
            print(f"   执行时间: {query_result.get('execution_time', 0):.2f}s")
        
        # 测试指标端点
        print("\n📈 测试指标端点...")
        response = await client.get(f"{base_url}/metrics")
        print(f"   状态码: {response.status_code}")
        if response.status_code == 200:
            metrics_text = response.text
            print(f"   指标数据长度: {len(metrics_text)} 字符")


async def performance_test():
    """性能测试"""
    print("\n🚀 开始性能测试...")
    
    base_url = "http://localhost:8000"
    concurrent_requests = 10
    
    async def single_request(client: httpx.AsyncClient, request_id: int):
        """单个请求"""
        start_time = time.time()
        try:
            response = await client.post(
                f"{base_url}/query",
                json={
                    "query": f"这是第 {request_id} 个测试请求",
                    "user_id": f"test_user_{request_id}"
                },
                timeout=30.0
            )
            duration = time.time() - start_time
            return {
                "request_id": request_id,
                "status_code": response.status_code,
                "duration": duration,
                "success": response.status_code == 200
            }
        except Exception as e:
            duration = time.time() - start_time
            return {
                "request_id": request_id,
                "status_code": 0,
                "duration": duration,
                "success": False,
                "error": str(e)
            }
    
    async with httpx.AsyncClient() as client:
        # 并发发送请求
        tasks = [
            single_request(client, i) 
            for i in range(concurrent_requests)
        ]
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # 分析结果
        successful_requests = [r for r in results if r["success"]]
        failed_requests = [r for r in results if not r["success"]]
        
        print(f"   总请求数: {len(results)}")
        print(f"   成功请求数: {len(successful_requests)}")
        print(f"   失败请求数: {len(failed_requests)}")
        print(f"   总耗时: {total_time:.2f}s")
        print(f"   平均响应时间: {sum(r['duration'] for r in successful_requests) / len(successful_requests):.2f}s" if successful_requests else "N/A")
        print(f"   请求/秒: {len(results) / total_time:.2f}")
        
        if failed_requests:
            print("\n❌ 失败请求详情:")
            for req in failed_requests[:3]:  # 只显示前3个
                print(f"   请求 {req['request_id']}: {req.get('error', '未知错误')}")


async def main():
    """主测试函数"""
    print("🧪 MCP生产客户端测试")
    print("=" * 50)
    
    try:
        # 基础API测试
        await test_api_endpoints()
        
        # 性能测试
        await performance_test()
        
        print("\n✅ 测试完成!")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        print("请确保服务器正在运行: python -m src.api.main")


if __name__ == "__main__":
    asyncio.run(main())