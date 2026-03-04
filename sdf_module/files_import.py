import os
import glob
import requests
import subprocess
import sys
import hashlib
import json
import sys
import csv
import yaml
import importlib.util
import logging
from openpyxl import load_workbook  # type: ignore
from datetime import datetime
import time
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import date
from lxml import etree #type: ignore
from proxy_config import *
import random
from lxml import html #type: ignore
import json
import math
import pdb
from time import sleep
import pika #type: ignore
import re
import pandas as pd  # type: ignore
from contextvars import ContextVar
# Base directory: project root (parent of sdf_module)
base_dir = str(Path(__file__).resolve().parent.parent)
CLOUDAMQP_URL = os.environ.get(
    "CLOUDAMQP_URL",
    "amqps://fwgxshpc:6VNXrVYFv3yAVEjPdsd001qClkj3JTAS@puffin.rmq2.cloudamqp.com/fwgxshpc",
)
