from mcp.server.fastmcp import FastMCP
import logging
from sublist3r import main as sublist3r_main
import nmap
import asyncio


mcp = FastMCP("Network Tools")


@mcp.tool(description="Find subdomains for a given domain.")
async def find_subdomain(domain: str) -> str:
    engines = "baidu,yahoo,google,bing,ask,threatcrowd,ssl,passivedns,netcraft,dnsdumpster,virustotal"

    # sublist3r.main is blocking; run it in a thread
    return await asyncio.to_thread(
        sublist3r_main, domain, 40, None, None, True, False, False, engines
    )


@mcp.tool(description="Find open ports and services for a given IP address or hostname.")
async def find_port_details(target: str) -> str:
    def _scan_target(t: str) -> str:
        scanner = nmap.PortScanner()
        scanner.scan(t)

        result = ""
        for host in scanner.all_hosts():
            result += f"Host: {host}\n"
            result += f"State: {scanner[host].state()}\n"
            for proto in scanner[host].all_protocols():
                result += f"Protocol: {proto}\n"
                for port, data in scanner[host][proto].items():
                    result += f"Port: {port} State: {data.get('state', 'unknown')}\n"
        return result or f"No results for {t}\n"

    return await asyncio.to_thread(_scan_target, target)


@mcp.tool(description="Find service fingerprint for a given link.")
async def find_service_fingerprint(link: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "whatweb", link,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode(errors="ignore") or stderr.decode(errors="ignore")
    except FileNotFoundError:
        return "Error: whatweb not found on system"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool(description="Find OSINT collection for a given domain.")
async def find_osint_collection(domain: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "theharvester", "-d", domain, "-l", "100", "-b", "bing,yahoo,duckduckgo",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode(errors="ignore") or stderr.decode(errors="ignore")
    except FileNotFoundError:
        return "Error: theharvester not found on system"
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting the MCP Server (SSE remote)")
    mcp.run(transport="sse")