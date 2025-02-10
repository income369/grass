#!/usr/bin/env python3
import asyncio
import random
import ssl
import json
import time
import uuid
import base64
import aiohttp
from datetime import datetime
from colorama import init, Fore, Style
from websockets_proxy import Proxy, proxy_connect

# Initialize colorama so that colors reset automatically.
init(autoreset=True)

# Optional: Use uvloop for improved performance (if available)
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

BANNER = """
   __  ______  ___  ______        __ 
  /  |/  / _ \/ _ \/_  __/__ ____/ / 
 / /|_/ / , _/ ___/ / / / -_) __/ _ \\
/_/  /_/_/|_/_/    /_/  \\__/\\__/_//_/
                                      
"""

EDGE_USERAGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.2365.57",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.2365.52",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.2365.46",
    # ... (other user agents)
]

HTTP_STATUS_CODES = {
    200: "OK",
    201: "Created", 
    202: "Accepted",
    204: "No Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden", 
    404: "Not Found",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout"
}

def colorful_log(proxy, device_id, message_type, message_content, is_sent=False, mode=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = Fore.GREEN if is_sent else Fore.BLUE
    action_color = Fore.YELLOW
    mode_color = Fore.LIGHTYELLOW_EX
    log_message = (
        f"{Fore.WHITE}[{timestamp}] "
        f"{Fore.MAGENTA}[Proxy: {proxy}] "
        f"{Fore.CYAN}[Device ID: {device_id}] "
        f"{action_color}[{message_type}] "
        f"{color}{message_content} "
        f"{mode_color}[{mode}]"
    )
    print(log_message)

async def connect_to_wss(socks5_proxy, user_id, mode):
    device_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, socks5_proxy + user_id))
    random_user_agent = random.choice(EDGE_USERAGENTS)
    colorful_log(
        proxy=socks5_proxy,  
        device_id=device_id, 
        message_type="INITIALIZATION", 
        message_content=f"User Agent: {random_user_agent} | Account: {user_id}",
        mode=mode
    )

    has_received_action = False
    is_authenticated = False
    backoff = 1  # initial reconnect delay

    while True:
        try:
            await asyncio.sleep(random.uniform(0.1, 1.0))
            custom_headers = {
                "User-Agent": random_user_agent,
                "Origin": "chrome-extension://lkbnfiajjmbhnfledhphioinpickokdi" if mode == "extension" else ""
            }
            custom_headers = {k: v for k, v in custom_headers.items() if v}
            
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            urilist = [
                "wss://proxy2.wynd.network:4444/",
                "wss://proxy2.wynd.network:4650/"
            ]
            uri = random.choice(urilist)
            server_hostname = uri.split("://")[1].split(":")[0]
            proxy_obj = Proxy.from_url(socks5_proxy)
            
            async with proxy_connect(uri, proxy=proxy_obj, ssl=ssl_context,
                                     server_hostname=server_hostname, extra_headers=custom_headers) as websocket:
                backoff = 1  # reset backoff after a successful connection

                async def send_ping():
                    while True:
                        if has_received_action:
                            send_message = json.dumps({
                                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, socks5_proxy)),
                                "version": "1.0.0",
                                "action": "PING",
                                "data": {}
                            })
                            colorful_log(
                                proxy=socks5_proxy,  
                                device_id=device_id, 
                                message_type="SENDING PING", 
                                message_content=send_message,
                                is_sent=True,
                                mode=mode
                            )
                            await websocket.send(send_message)
                        await asyncio.sleep(5)

                ping_task = asyncio.create_task(send_ping())

                while True:
                    if is_authenticated and not has_received_action:
                        waiting_for = "HTTP_REQUEST" if mode == "extension" else "OPEN_TUNNEL"
                        colorful_log(
                            proxy=socks5_proxy,
                            device_id=device_id,
                            message_type="AUTHENTICATED | WAITING",
                            message_content=f"Waiting for {waiting_for}",
                            mode=mode
                        )
                    response = await websocket.recv()
                    message = json.loads(response)
                    
                    colorful_log(
                        proxy=socks5_proxy, 
                        device_id=device_id, 
                        message_type="RECEIVED", 
                        message_content=json.dumps(message),
                        mode=mode
                    )

                    action = message.get("action")
                    if action == "AUTH":
                        auth_response = {
                            "id": message["id"],
                            "origin_action": "AUTH",
                            "result": {
                                "browser_id": device_id,
                                "user_id": user_id,
                                "user_agent": random_user_agent,
                                "timestamp": int(time.time()),
                                "device_type": "extension" if mode == "extension" else "desktop",
                                "version": "4.26.2" if mode == "extension" else "4.30.0"
                            }
                        }
                        if mode == "extension":
                            auth_response["result"]["extension_id"] = "lkbnfiajjmbhnfledhphioinpickokdi"
                        
                        colorful_log(
                            proxy=socks5_proxy,  
                            device_id=device_id, 
                            message_type="AUTHENTICATING", 
                            message_content=json.dumps(auth_response),
                            is_sent=True,
                            mode=mode
                        )
                        await websocket.send(json.dumps(auth_response))
                        is_authenticated = True

                    elif action in ["HTTP_REQUEST", "OPEN_TUNNEL"]:
                        has_received_action = True
                        request_data = message.get("data", {})
                        headers = {
                            "User-Agent": custom_headers.get("User-Agent"),
                            "Content-Type": "application/json; charset=utf-8"
                        }
                        async with aiohttp.ClientSession() as session:
                            async with session.get(request_data.get("url", ""), headers=headers) as api_response:
                                content = await api_response.text()
                                encoded_body = base64.b64encode(content.encode()).decode()
                                status_text = HTTP_STATUS_CODES.get(api_response.status, "")
                                http_response = {
                                    "id": message["id"],
                                    "origin_action": action,
                                    "result": {
                                        "url": request_data.get("url", ""),
                                        "status": api_response.status,
                                        "status_text": status_text,
                                        "headers": dict(api_response.headers),
                                        "body": encoded_body
                                    }
                                }
                                colorful_log(
                                    proxy=socks5_proxy,
                                    device_id=device_id,
                                    message_type="OPENING PING ACCESS",
                                    message_content=json.dumps(http_response),
                                    is_sent=True,
                                    mode=mode
                                )
                                await websocket.send(json.dumps(http_response))
                    elif action == "PONG":
                        pong_response = {"id": message["id"], "origin_action": "PONG"}
                        colorful_log(
                            proxy=socks5_proxy, 
                            device_id=device_id, 
                            message_type="SENDING PONG", 
                            message_content=json.dumps(pong_response),
                            is_sent=True,
                            mode=mode
                        )
                        await websocket.send(json.dumps(pong_response))
                ping_task.cancel()

        except Exception as e:
            colorful_log(
                proxy=socks5_proxy, 
                device_id=device_id, 
                message_type="ERROR", 
                message_content=str(e),
                mode=mode
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

async def main():
    print(f"{Fore.CYAN}{BANNER}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}MRP Tech | Grass Script Updated{Style.RESET_ALL}")
    
    print(f"{Fore.GREEN}Select Mode:{Style.RESET_ALL}")
    print("1. Extension Mode")
    print("2. Desktop Mode")
    while True:
        mode_choice = input("Enter your choice (1/2): ").strip()
        if mode_choice in ['1', '2']:
            break
        print(f"{Fore.RED}Invalid choice. Please enter 1 or 2.{Style.RESET_ALL}")
    mode = "extension" if mode_choice == "1" else "desktop"
    print(f"{Fore.GREEN}Selected mode: {mode}{Style.RESET_ALL}")
    
    # Prompt for multiple user IDs (comma-separated)
    user_input = input('Enter your user IDs (comma separated): ')
    user_ids = [uid.strip() for uid in user_input.split(",") if uid.strip()]
    
    with open('proxy_list.txt', 'r') as file:
        local_proxies = [line.strip() for line in file if line.strip()]
    print(f"{Fore.YELLOW}Total Proxies: {len(local_proxies)}{Style.RESET_ALL}")
    
    # Set how many parallel connections per proxy per account
    PARALLEL_CONNECTIONS = 10
    tasks = []
    for proxy in local_proxies:
        for user_id in user_ids:
            for _ in range(PARALLEL_CONNECTIONS):
                tasks.append(asyncio.create_task(connect_to_wss(proxy, user_id, mode)))
    
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    asyncio.run(main())
