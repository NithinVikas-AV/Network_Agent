import re
import nmap
import shutil
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
from mcp.server.fastmcp import FastMCP
from sublist3r import main as sublist3r_main

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

def run_gobuster_auto(mode: str,
                      target: str,
                      wordlist: str,
                      threads: int = 20,
                      extra_args: Optional[List[str]] = None,
                      print_success_only: bool = False,
                      include_statuses: Optional[List[int]] = None,
                      force_use_m_flag: Optional[bool] = None
                      ) -> Tuple[int, List[str], str]:
    """
    Run gobuster with auto-fallback between:
      - positional subcommand style:  gobuster dir -u <url> -w <wordlist> ...
      - -m flag style:              gobuster -m dir -u <url> -w <wordlist> ...
    Returns (exit_code, captured_lines, which_invocation_used)
    """
    if shutil.which("gobuster") is None:
        raise RuntimeError("gobuster not found in PATH. Install it or add to PATH.")

    if extra_args is None:
        extra_args = []
    if include_statuses is None:
        include_statuses = [200, 204, 301, 302, 307, 403]

    # Validate wordlist presence unless it's '-' (stdin)
    if wordlist != "-" and wordlist:
        p = Path(wordlist)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Wordlist not found: {wordlist}")

    # Helper to run and capture both stdout+stderr
    def _run(cmd: List[str]) -> Tuple[int, List[str], str]:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out = proc.stdout or ""
        lines = out.splitlines()
        # Optionally filter printed lines based on status presence
        if print_success_only:
            status_re = re.compile(r"(\bstatus[:\s]*)(\d{3})", re.IGNORECASE)
            for line in lines:
                m = status_re.search(line)
                if m:
                    try:
                        st = int(m.group(2))
                    except:
                        st = None
                    if st in include_statuses:
                        print(line)
        else:
            for line in lines:
                print(line)
        return proc.returncode, lines, out

    # Construct invocations
    positional_cmd = ["gobuster", mode, "-u", target, "-w", wordlist, "-t", str(threads)] + extra_args
    flag_cmd = ["gobuster", "-m", mode, "-u", target, "-w", wordlist, "-t", str(threads)] + extra_args

    if force_use_m_flag is True:
        attempts = [flag_cmd]
    elif force_use_m_flag is False:
        attempts = [positional_cmd]
    else:
        attempts = [positional_cmd, flag_cmd]

    last_ret = 1
    last_lines = []
    last_out = ""
    for i, cmd in enumerate(attempts, start=1):
        print("Executing:", " ".join(cmd))
        retcode, lines, full = _run(cmd)
        last_ret, last_lines, last_out = retcode, lines, full

        # Treat return codes 0 and 1 as acceptable success (some gobuster versions use 1)
        if retcode in (0, 1):
            which = "positional" if cmd == positional_cmd else "-m-flag"
            return retcode, lines, which

        # If non-zero, check for parsing/missing-arg errors and allow fallback
        joined = "\n".join(lines).lower()
        if any(kw in joined for kw in (
            "wordlist (-w): must be specified",
            "url/domain (-u): must be specified",
            "unknown command",
            "invalid subcommand",
            "error parsing",
            "no such file or directory",
        )):
            # try next attempt if available
            print(f"[Invocation {i} returned argument/parse error — trying next invocation if available]")
            continue
        else:
            # other error — don't fallback further
            which = "positional" if cmd == positional_cmd else "-m-flag"
            return retcode, lines, which

    # exhausted attempts
    which = "positional_then_flag" if len(attempts) > 1 else ("-m-flag" if force_use_m_flag else "positional")
    return last_ret, last_lines, which


# MCP async wrapper that accepts only `target` from the client
# Put this in your MCP server (alongside other @mcp.tool definitions).
# All other args are constants and not required from the client.
DEFAULT_GOBUSTER_MODE = "dir"
DEFAULT_GOBUSTER_THREADS = 20
DEFAULT_GOBUSTER_EXTRA_ARGS = ["-e", "-r"]  # expand (show extensions), follow redirects
# try a few common wordlist locations (first that exists will be used)
COMMON_WORDLIST_CANDIDATES = [
    "/usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt",
    "/usr/share/wordlists/dirb/common.txt",
    "/usr/share/wordlists/common.txt",
    "common.txt",  # allow local fallback (developer should ensure it exists)
]

def _select_wordlist() -> Optional[str]:
    for candidate in COMMON_WORDLIST_CANDIDATES:
        p = Path(candidate)
        if p.exists() and p.is_file():
            return str(p)
    return None

# Example MCP tool: only `target` argument required by client
@mcp.tool(description="Run gobuster directory enumeration (only pass target).")
async def run_gobuster(target: str) -> str:
    """
    Client only provides `target` (URL or domain). Everything else is constant/handled server-side.
    """
    wordlist = _select_wordlist()
    if not wordlist:
        return ("Error: no default wordlist found on server. Please install a wordlist or place 'common.txt' "
                "in the working directory. Candidates checked: " + ", ".join(COMMON_WORDLIST_CANDIDATES))

    try:
        retcode, lines, which = await asyncio.to_thread(
            run_gobuster_auto,
            DEFAULT_GOBUSTER_MODE,
            target,
            wordlist,
            DEFAULT_GOBUSTER_THREADS,
            DEFAULT_GOBUSTER_EXTRA_ARGS,
            False,    # print_success_only (server prints anyway)
            None,     # include_statuses
            None      # force_use_m_flag (auto)
        )
        header = f"Exit code: {retcode}\nInvocation: {which}\nWordlist: {wordlist}\n\n"
        body = "\n".join(lines) if lines else "(no output)"
        return header + body
    except FileNotFoundError as fnf:
        return f"Error: {fnf}"
    except RuntimeError as rexc:
        return f"Runtime Error: {rexc}"
    except Exception as e:
        return f"Unexpected Error: {e}"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting the MCP Server (SSE remote)")
    mcp.run(transport="sse")