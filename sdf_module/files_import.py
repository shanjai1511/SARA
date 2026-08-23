from __future__ import annotations

import csv
import glob
import hashlib
import importlib.util
import json
import logging
import math
import os
import random
import re
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from time import sleep
from typing import Any, Dict, List, Optional, Tuple

# pandas is an optional dependency used only by the dashboard preview
# import locally where needed to avoid forcing it to all scripts
import pika  # type: ignore
import requests
import yaml
from bs4 import BeautifulSoup
from lxml import etree, html  # type: ignore

from proxy_config import webshare_proxy  # type: ignore  # explicit proxy list

# Base directory: project root (parent of sdf_module)
base_dir = Path(__file__).resolve().parent.parent

# CLOUDAMQP_URL is loaded from config.settings to ensure it is always
# present and never falls back to a hardcoded credential.
from config.settings import settings as _settings  # noqa: E402
CLOUDAMQP_URL = _settings.CLOUDAMQP_URL


def normalize_class_name(project: str, site: str) -> str:
    """Return a PascalCase class name for a given project/site pair.

    Example: project="commerce_crawl", site="styleunion_com"  ->
    "StyleunionComCommerceCrawl".
    """
    raw = f"{site}_{project}"
    return "".join(word.capitalize() for word in raw.split("_"))
