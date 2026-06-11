from pathlib import Path

from .config import OUTPUT_DIR


def text_of(message) -> str:
    if message is None:
        return ""
    return "\n".join(
        block.text for block in message.content if block.type == "text"
    ).strip()


def output_path(filename: str) -> Path:
    directory = Path(OUTPUT_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / Path(filename).name
