import os
import glob
import requests
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
import pika #type: ignore
import re
base_dir = "C:/Users/shanj/OneDrive/Desktop/SARA"
CLOUDAMQP_URL = "amqps://fwgxshpc:6VNXrVYFv3yAVEjPdsd001qClkj3JTAS@puffin.rmq2.cloudamqp.com/fwgxshpc"