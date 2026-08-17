from __future__ import annotations

import re
import shlex
import unicodedata


def normalize_command(command: str) -> str:
    """Normalize command spelling without changing its intended operation."""

    normalized = unicodedata.normalize("NFKC", command)
    normalized = re.sub(r"\\\r?\n", " ", normalized)
    normalized = re.sub(r"`\r?\n", " ", normalized)
    normalized = re.sub(r"\^\r?\n", " ", normalized)
    # POSIX shlex treats backslashes as escapes. Normalize Windows drive roots
    # first so destructive targets such as C:\\* retain their path separator.
    normalized = re.sub(r"(?i)\b([a-z]):\\", r"\1:/", normalized)
    return " ".join(normalized.strip().split())


def split_shell_segments(command: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"\|\||&&|[;|]", command) if segment.strip()]


def split_pipeline(command: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"(?<!\|)\|(?!\|)", command) if segment.strip()]


def tokenize(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return re.findall(r'"[^"]*"|\'[^\']*\'|\S+', command)


def executable_index(tokens: list[str]) -> int | None:
    index = 0
    while index < len(tokens):
        if re.fullmatch(r"(?:\$env:)?[A-Za-z_][A-Za-z0-9_]*=.*", tokens[index], re.IGNORECASE):
            index += 1
            continue
        executable = basename(tokens[index])
        if executable in {"sudo", "command", "env"}:
            index += 1
            while index < len(tokens) and "=" in tokens[index] and not tokens[index].startswith(("/", "./")):
                index += 1
            continue
        return index
    return None


def contains_executable(tokens: list[str], names: set[str] | frozenset[str]) -> bool:
    return any(basename(token) in names for token in tokens)


def prints_environment(tokens: list[str]) -> bool:
    index = 0
    while index < len(tokens) and basename(tokens[index]) in {"sudo", "command"}:
        index += 1
    if index >= len(tokens):
        return False
    executable = basename(tokens[index])
    if executable == "printenv":
        return len(tokens) == index + 1
    if executable != "env":
        return False

    ignore_environment = False
    assignments = False
    for raw_arg in tokens[index + 1 :]:
        arg = raw_arg.casefold()
        if arg in {"--help", "--version"}:
            return False
        if arg in {"-i", "--ignore-environment"}:
            ignore_environment = True
            continue
        if arg.startswith("-"):
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", raw_arg):
            assignments = True
            continue
        return False
    return assignments or not ignore_environment


def basename(token: str) -> str:
    return token.strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].casefold().removesuffix(".exe")


def flags_and_targets(args: list[str], *, slash_flags: bool = False) -> tuple[set[str], list[str]]:
    flags: set[str] = set()
    targets: list[str] = []
    stop_flags = False
    for raw in args:
        value = raw.strip("\"'")
        if value == "--":
            stop_flags = True
            continue
        if not stop_flags and value.startswith("--"):
            flags.add(value[2:].casefold())
            continue
        if not stop_flags and value.startswith("-") and len(value) > 1:
            flag_body = value[1:]
            if flag_body.casefold() in {"recurse", "recursive", "force", "confirm", "whatif"}:
                flags.add(flag_body.casefold())
            elif len(flag_body) == 1:
                flags.add(flag_body)
            else:
                flags.update(flag_body)
            continue
        if slash_flags and value.startswith("/") and len(value) == 2 and value[1].isalpha():
            flags.add(value[1].casefold())
            continue
        targets.append(value)
    return flags, targets


def is_dangerous_target(target: str, dangerous_targets: set[str]) -> bool:
    normalized = target.strip().strip("\"'").replace("\\", "/").casefold()
    normalized = re.sub(r"/+$", "/", normalized) if normalized not in {"./", "/"} else normalized
    if normalized in dangerous_targets:
        return True
    if re.fullmatch(r"[a-z]:/(?:\*|\*\*|)?", normalized):
        return True
    return normalized.startswith(("$home/", "${home}/", "$pwd/", "${pwd}/", "%userprofile%/")) and normalized.endswith(
        ("*", "**")
    )


def wrapper_payload(tokens: list[str]) -> str | None:
    """Return the command passed to a supported shell wrapper, if present."""

    index = executable_index(tokens)
    if index is None:
        return None
    executable = basename(tokens[index])
    args = tokens[index + 1 :]
    if executable in {"bash", "sh", "zsh"}:
        return _payload_after_flag(args, {"-c", "--command"})
    if executable == "cmd":
        return _payload_after_flag(args, {"/c", "-c"}, join_remaining=True)
    if executable in {"pwsh", "powershell"}:
        return _payload_after_flag(args, {"-c", "-command", "/c"}, join_remaining=True)
    return None


def has_encoded_powershell(tokens: list[str]) -> bool:
    index = executable_index(tokens)
    if index is None or basename(tokens[index]) not in {"pwsh", "powershell"}:
        return False
    return any(
        arg.casefold() in {"-e", "-ec", "-enc", "-encodedcommand"} or arg.casefold().startswith("-encodedcommand=")
        for arg in tokens[index + 1 :]
    )


def _payload_after_flag(
    args: list[str],
    flags: set[str],
    *,
    join_remaining: bool = False,
) -> str | None:
    for index, arg in enumerate(args):
        if arg.casefold() not in flags or index + 1 >= len(args):
            continue
        payload = args[index + 1 :]
        return " ".join(payload) if join_remaining else payload[0]
    return None
