"""화랑 Grid 에이전트 설치 패키지

설치:
    pip install hwarang-agent

또는 개발 모드:
    pip install -e .

사용:
    hwarang-agent                    # 기본 실행
    hwarang-agent --preset full      # Full 티어
    hwarang-agent --show-config      # 설정 확인
    hwarang-agent --daemon           # 백그라운드 실행
"""

from setuptools import setup, find_packages

setup(
    name="hwarang-agent",
    version="1.0.0",
    description="화랑 AI Grid 에이전트 - GPU 공유 네트워크 참여",
    long_description=open("README.md", encoding="utf-8").read() if __import__("os").path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="Persismore",
    author_email="dev@persismore.com",
    url="https://hwarang.ai",
    project_urls={
        "Homepage": "https://hwarang.ai",
        "Documentation": "https://docs.hwarang.ai/agent",
        "Source": "https://github.com/persismore/hwarang-agent",
    },
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.25.0",
    ],
    extras_require={
        "gpu": [
            "torch>=2.0",
            "transformers>=4.40",
            "peft>=0.10",
            "trl>=0.8",
            "bitsandbytes>=0.43",
            "safetensors>=0.4",
            "accelerate>=0.30",
        ],
        "full": [
            "torch>=2.0",
            "transformers>=4.40",
            "peft>=0.10",
            "trl>=0.8",
            "bitsandbytes>=0.43",
            "safetensors>=0.4",
            "accelerate>=0.30",
            "sentence-transformers>=2.7",
            "chromadb>=0.5",
        ],
    },
    entry_points={
        "console_scripts": [
            # 신규: 명령어 중심 CLI (init/start/pause/earnings/...)
            "hwarang-agent=cli:main",
            # 기존: 직접 실행용 (legacy)
            "hwarang-agent-daemon=agent_main:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
