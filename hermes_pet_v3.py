#!/usr/bin/env python3
# Thin backward-compatibility stub — delegates to modular 11/ package
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '11'))
from ui import main
main()
