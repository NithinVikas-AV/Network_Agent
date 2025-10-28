import subprocess
import shutil
import re
from pathlib import Path
from typing import List, Optional, Tuple

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
    Run gobuster, auto-fallback between gobuster dir -u ... style and gobuster -m dir -u ... style.
    Returns (exit_code, captured_lines, which_invocation_used)
    - mode: 'dir' / 'dns' / 'vhost'
    - target: URL (for dir/vhost) or domain (for dns)
    - wordlist: path to wordlist (use '-' for stdin)
    - extra_args: list of extra flags, e.g. ['-e','-r']
    - print_success_only: if True, prints only lines with statuses in include_statuses
    - force_use_m_flag: if True always use "-m", if False always use positional; if None auto try both
    """
    if shutil.which("gobuster") is None:
        raise RuntimeError("gobuster not found in PATH. Install it or add to PATH.")

    if extra_args is None:
        extra_args = []
    if include_statuses is None:
        include_statuses = [200,204,301,302,307,403]

    # Validate wordlist presence unless it's '-' (stdin)
    if wordlist != "-" and wordlist:
        p = Path(wordlist)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Wordlist not found: {wordlist}")

    # Helper to run and capture both stdout+stderr
    def _run(cmd: List[str]) -> Tuple[int, List[str], str]:
        # Use subprocess.run to get full output at once (safer for error detection)
        print("Executing:", " ".join(cmd))
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        lines = proc.stdout.splitlines()
        # Print lines according to print_success_only
        status_re = re.compile(r"Status:\s*(\d{3})", re.IGNORECASE)
        for line in lines:
            if not print_success_only:
                print(line)
            else:
                m = status_re.search(line)
                if m:
                    try:
                        st = int(m.group(1))
                    except:
                        st = None
                    if st in include_statuses:
                        print(line)
        return proc.returncode, lines, proc.stdout

    # Build positional invocation (the style you ran in terminal)
    # Example: ["gobuster", "dir", "-u", "https://ecampus.psgtech.ac.in", "-w", "/path/common.txt", "-t", "20", "-e", "-r"]
    positional_cmd = ["gobuster", mode, "-u", target, "-w", wordlist, "-t", str(threads)] + extra_args

    # Build -m flag invocation: ["gobuster", "-m", "dir", "-u", target, ...]
    flag_cmd = ["gobuster", "-m", mode, "-u", target, "-w", wordlist, "-t", str(threads)] + extra_args

    # Choose order depending on force_use_m_flag
    attempts = []
    if force_use_m_flag is True:
        attempts = [flag_cmd]
    elif force_use_m_flag is False:
        attempts = [positional_cmd]
    else:
        # try positional first (matches your terminal), then flag style fallback
        attempts = [positional_cmd, flag_cmd]

    last_stdout = ""
    for i, cmd in enumerate(attempts, start=1):
        try:
            retcode, lines, full = _run(cmd)
            last_stdout = full
        except FileNotFoundError as e:
            raise
        # If gobuster returned success (0) — great, return it
        if retcode == 0:
            which = "positional" if cmd is positional_cmd else "-m-flag"
            return retcode, lines, which
        # If gobuster returned non-zero, check for the exact common parsing error
        joined = "\n".join(lines).lower()
        if "wordlist (-w): must be specified" in joined or "url/domain (-u): must be specified" in joined:
            print(f"[Invocation {i} returned the missing-arg error; will try next invocation if available]")
            # continue to next attempt
            continue
        else:
            # got some other error — return it (no fallback) but include which tried
            which = "positional" if cmd is positional_cmd else "-m-flag"
            return retcode, lines, which

    # If we exhausted attempts, return last result
    which = "positional_then_flag" if len(attempts) > 1 else ("-m-flag" if force_use_m_flag else "positional")
    return retcode, lines, which


# -------------------------
# Example usage — paste and run:
if __name__ == "__main__":
    mode = "dir"
    target = "https://ecampus.psgtech.ac.in"
    wordlist = "common.txt"   # change to your path or '/Users/harsi/Downloads/common.txt'
    extra_args = ["-e", "-r"]          # expanded + follow redirects
    try:
        code, captured_lines, which = run_gobuster_auto(mode, target, wordlist, threads=20,
                                                        extra_args=extra_args,
                                                        print_success_only=False,
                                                        force_use_m_flag=None)
        print(f"\nFinished. exit_code={code}, invocation_used={which}, captured_lines={len(captured_lines)}")
    except Exception as ex:
        print("Error:", ex)