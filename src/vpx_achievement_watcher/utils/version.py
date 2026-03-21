WATCHER_VERSION = "2.6"

def _parse_version(v: str) -> tuple:
    return tuple(int(x) for x in str(v).split(".") if x.isdigit())
