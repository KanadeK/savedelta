from __future__ import annotations

from savedelta.demo import create_demo


if __name__ == "__main__":
    result = create_demo("example-output", force=True)
    print(result["html_report"])
