# 24 Game Trainer

A Kivy-based application for training the 24 game, with an efficient C++ solver backend.

## Requirements

- Python 3.7+
- CMake 3.4+
- C++ compiler with C++17 support
- pybind11

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Build the C++ module:
```bash
cd lib
mkdir build
cd build
cmake ..
cmake --build .
```

3. Run the application:
```bash
python src/main.py
```

## Features

- Fast C++-based solver for validating 24 game combinations
- Modern Kivy UI with smooth animations
- Real-time validation of number combinations
- Score tracking and timer functionality

