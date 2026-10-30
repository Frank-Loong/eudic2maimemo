"""PyInstaller 入口。

打包好的单文件程序里没有 Python 解释器环境，所以这里直接调 CLI，
不做任何依赖当前工作目录的事情。
"""

import sys

from eudic2maimemo.cli import main

if __name__ == "__main__":
    sys.exit(main())
