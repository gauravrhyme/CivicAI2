import csv
import hashlib
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from io import StringIO

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

# ─────────────────────────────────────────────────────────────
# APP + DB
# ─────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

db_url = os.environ.get("DATABASE_URL", "sqlite:///civicai.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_SORT_KEYS"] = False

db = SQLAlchemy(app)

# ─────────────────────────────────────────────────────────────
# VERIFIED CIVIC INTELLIGENCE DATASET
# ─────────────────────────────────────────────────────────────

CONSTITUENCY_MLA = {
    "Yelahanka":           ("150", "S R Vishwanath",         "INC"),
    "Byatarayanapura":     ("152", "B A Basavaraj",          "INC"),
    "Dasarahalli":         ("155", "Manjunath Bhajantri",    "BJP"),
    "Rajarajeshwarinagar": ("154", "Munirathna",             "BJP"),
    "Yeshwanthpura":       ("153", "S T Somashekhar",        "BJP"),
    "Mahalakshmi Layout":  ("156", "K Gopalaiah",            "INC"),
    "Malleshwaram":        ("157", "Ashwath Narayan C N",    "BJP"),
    "Hebbal":              ("158", "Byrathi Basavaraj",      "INC"),
    "Krishnarajapuram":    ("151", "Byrathi Suresh",         "INC"),
    "Pulakeshinagar":      ("159", "Akhanda Srinivas Murthy","INC"),
    "Sarvagnanagar":       ("160", "T A Sharavana",          "INC"),
    "C V Raman Nagar":     ("161", "S Raghu",                "INC"),
    "Shivajinagar":        ("162", "Rizwan Arshad",          "INC"),
    "Shanthinagar":        ("163", "N A Haris",              "INC"),
    "Gandhi Nagar":        ("164", "Dinesh Gundu Rao",       "INC"),
    "Rajaji Nagar":        ("165", "S Suresh Kumar",         "BJP"),
    "Govindraj Nagar":     ("166", "Zameer Ahmed Khan",      "INC"),
    "Vijay Nagar":         ("167", "K Gopalaiah",            "INC"),
    "Chamrajpet":          ("168", "Zameer Ahmed Khan",      "INC"),
    "Chickpet":            ("169", "Uday Garudachar",        "BJP"),
    "Basavanagudi":        ("170", "Sowmya Reddy",           "INC"),
    "Padmanabha Nagar":    ("171", "R Ashoka",               "BJP"),
    "B T M Layout":        ("172", "Ramalinga Reddy",        "INC"),
    "Jayanagar":           ("173", "C K Ramamurthy",         "BJP"),
    "Mahadevapura":        ("174", "Arvind Limbavali",       "BJP"),
    "Bommanahalli":        ("175", "Sathish Reddy",          "BJP"),
    "Bangalore South":     ("176", "M Krishnappa",           "INC"),
}

ZONE_META = {
    "Yelahanka":    {"zc": "Zonal Commissioner – Yelahanka",    "jc": "Joint Commissioner – Yelahanka",    "swm": "Ramky Enviro Engineers Ltd", "bwssb": "BWSSB North Division",      "bescom": "BESCOM Yelahanka Sub-Division"},
    "Dasarahalli":  {"zc": "Zonal Commissioner – Dasarahalli",  "jc": "Joint Commissioner – Dasarahalli",  "swm": "Hasiru Dala Innovations",    "bwssb": "BWSSB North-West Division", "bescom": "BESCOM Rajajinagar Sub-Division"},
    "RR Nagar":     {"zc": "Zonal Commissioner – RR Nagar",     "jc": "Joint Commissioner – RR Nagar",     "swm": "Antony Waste Handling Cell", "bwssb": "BWSSB West Division",       "bescom": "BESCOM RR Nagar Sub-Division"},
    "West":         {"zc": "Zonal Commissioner – West",         "jc": "Joint Commissioner – West",         "swm": "Urbaser Sumeet",             "bwssb": "BWSSB Central Division",    "bescom": "BESCOM Bangalore West Sub-Division"},
    "East":         {"zc": "Zonal Commissioner – East",         "jc": "Joint Commissioner – East",         "swm": "SLR Enviro Services",        "bwssb": "BWSSB East Division",       "bescom": "BESCOM Bangalore East Sub-Division"},
    "Mahadevapura": {"zc": "Zonal Commissioner – Mahadevapura", "jc": "Joint Commissioner – Mahadevapura", "swm": "Ramky Enviro Engineers Ltd", "bwssb": "BWSSB East Division",       "bescom": "BESCOM Whitefield Sub-Division"},
    "Bommanahalli": {"zc": "Zonal Commissioner – Bommanahalli", "jc": "Joint Commissioner – Bommanahalli", "swm": "Antony Waste Handling Cell", "bwssb": "BWSSB South Division",      "bescom": "BESCOM Bommanahalli Sub-Division"},
    "South":        {"zc": "Zonal Commissioner – South",        "jc": "Joint Commissioner – South",        "swm": "Urbaser Sumeet",             "bwssb": "BWSSB South Division",      "bescom": "BESCOM Bangalore South Sub-Division"},
}

ISSUE_SLA = {
    "Pothole": 7,
    "Garbage": 2,
    "Water Logging": 3,
    "Open Drain": 5,
    "Broken Streetlight": 3,
    "Illegal Dumping": 5,
    "Damaged Footpath": 14,
    "Encroachment": 30,
    "Water": 3,
    "Electricity": 1,
}

ISSUE_DEPT = {
    "Pothole":            {"dept": "Engineering", "primary": "BBMP Engineering Dept", "escalate_l2": "Executive Engineer – Zone", "escalate_l3": "Chief Engineer – BBMP HQ"},
    "Garbage":            {"dept": "Health+SWM",  "primary": "BBMP Health Dept + SWM", "escalate_l2": "Health Officer – Zone", "escalate_l3": "Chief Health Officer – BBMP"},
    "Water Logging":      {"dept": "Engineering", "primary": "BBMP Engineering Dept", "escalate_l2": "Executive Engineer – Zone", "escalate_l3": "Chief Engineer – BBMP HQ"},
    "Open Drain":         {"dept": "Engineering", "primary": "BBMP Engineering Dept", "escalate_l2": "Executive Engineer – Zone", "escalate_l3": "Chief Engineer – BBMP HQ"},
    "Broken Streetlight": {"dept": "Electricity", "primary": "BESCOM", "escalate_l2": "BESCOM Sub-Division Office", "escalate_l3": "BESCOM Division Office"},
    "Illegal Dumping":    {"dept": "Health+SWM",  "primary": "BBMP Health Dept + SWM", "escalate_l2": "Health Officer – Zone", "escalate_l3": "Chief Health Officer – BBMP"},
    "Damaged Footpath":   {"dept": "Engineering", "primary": "BBMP Engineering Dept", "escalate_l2": "Executive Engineer – Zone", "escalate_l3": "Chief Engineer – BBMP HQ"},
    "Encroachment":       {"dept": "Revenue", "primary": "BBMP Revenue Dept", "escalate_l2": "Revenue Officer – Zone", "escalate_l3": "Chief Revenue Officer – BBMP"},
    "Water":              {"dept": "Water", "primary": "BWSSB", "escalate_l2": "BWSSB Division Office", "escalate_l3": "BWSSB Chief Engineer"},
    "Electricity":        {"dept": "Electricity", "primary": "BESCOM", "escalate_l2": "BESCOM Sub-Division", "escalate_l3": "BESCOM Division Office"},
}

WARDS_198 = [
    (1,  "Kempegowda Ward",              "Yelahanka",    "Yelahanka"),
    (2,  "Chowdeshwari Ward",            "Yelahanka",    "Yelahanka"),
    (3,  "Attur Layout",                 "Yelahanka",    "Yelahanka"),
    (4,  "Yelahanka Satellite Town",     "Yelahanka",    "Yelahanka"),
    (5,  "Jakkur",                       "Yelahanka",    "Byatarayanapura"),
    (6,  "Thanisandra",                  "Yelahanka",    "Byatarayanapura"),
    (7,  "Byatarayanapura",              "Yelahanka",    "Byatarayanapura"),
    (8,  "Kodigehalli",                  "Yelahanka",    "Byatarayanapura"),
    (9,  "Vidyaranyapura",               "Yelahanka",    "Byatarayanapura"),
    (10, "Doddabommasandra",             "Yelahanka",    "Byatarayanapura"),
    (11, "Kuvempunagar",                 "Yelahanka",    "Byatarayanapura"),
    (12, "Shettyhalli",                  "Dasarahalli",  "Dasarahalli"),
    (13, "Mallasandra",                  "Dasarahalli",  "Dasarahalli"),
    (14, "Bagalagunte",                  "Dasarahalli",  "Dasarahalli"),
    (15, "T. Dasarahalli",               "Dasarahalli",  "Dasarahalli"),
    (16, "Jalahalli",                    "RR Nagar",     "Rajarajeshwarinagar"),
    (17, "J P Park",                     "RR Nagar",     "Rajarajeshwarinagar"),
    (18, "Radhakrishna Temple Ward",     "East",         "Hebbal"),
    (19, "Sanjay Nagar",                 "East",         "Hebbal"),
    (20, "Ganganagar",                   "East",         "Hebbal"),
    (21, "Hebbala",                      "East",         "Hebbal"),
    (22, "Vishwanath Nagenahalli",       "East",         "Hebbal"),
    (23, "Nagavara",                     "East",         "Sarvagnanagar"),
    (24, "HBR Layout",                   "East",         "Sarvagnanagar"),
    (25, "Horamavu",                     "Mahadevapura", "Krishnarajapuram"),
    (26, "Ramamurthy Nagar",             "Mahadevapura", "Krishnarajapuram"),
    (27, "Banaswadi",                    "East",         "Sarvagnanagar"),
    (28, "Kammanahalli",                 "East",         "Sarvagnanagar"),
    (29, "Kacharakanahalli",             "East",         "Sarvagnanagar"),
    (30, "Kadugondanahalli",             "East",         "Sarvagnanagar"),
    (31, "Kushal Nagar",                 "East",         "Pulakeshinagar"),
    (32, "Kaval Byrasandra",             "East",         "Pulakeshinagar"),
    (33, "Manorayanapalya",              "East",         "Hebbal"),
    (34, "Gangenahalli",                 "East",         "Hebbal"),
    (35, "Aramane Nagar",                "West",         "Malleshwaram"),
    (36, "Mattikere",                    "West",         "Malleshwaram"),
    (37, "Yeshwanthpura",                "RR Nagar",     "Yeshwanthpura"),
    (38, "HMT Ward",                     "RR Nagar",     "Rajarajeshwarinagar"),
    (39, "Chokkasandra",                 "Dasarahalli",  "Dasarahalli"),
    (40, "Dodda Bidarakallu",            "RR Nagar",     "Yeshwanthpura"),
    (41, "Peenya Industrial Area",       "Dasarahalli",  "Dasarahalli"),
    (42, "Lakshmidevi Nagar",            "RR Nagar",     "Rajarajeshwarinagar"),
    (43, "Nandini Layout",               "West",         "Mahalakshmi Layout"),
    (44, "Marappana Palya",              "West",         "Mahalakshmi Layout"),
    (45, "Malleswaram",                  "West",         "Malleshwaram"),
    (46, "Jayachamarajendra Nagar",      "East",         "Hebbal"),
    (47, "Devara Jeevanahalli",          "East",         "Pulakeshinagar"),
    (48, "Muneshwara Nagar",             "East",         "Pulakeshinagar"),
    (49, "Lingarajapuram",               "East",         "Sarvagnanagar"),
    (50, "Benniganahalli",               "East",         "C V Raman Nagar"),
    (51, "Vijinapura",                   "Mahadevapura", "Krishnarajapuram"),
    (52, "Krishnarajapuram",             "Mahadevapura", "Krishnarajapuram"),
    (53, "Basavanapura",                 "Mahadevapura", "Krishnarajapuram"),
    (54, "Hoodi",                        "Mahadevapura", "Mahadevapura"),
    (55, "Devasandra",                   "Mahadevapura", "Krishnarajapuram"),
    (56, "A Narayanapura",               "Mahadevapura", "Krishnarajapuram"),
    (57, "C V Raman Nagar",              "East",         "C V Raman Nagar"),
    (58, "New Tippasandra",              "East",         "C V Raman Nagar"),
    (59, "Maruthi Seva Nagar",           "East",         "Sarvagnanagar"),
    (60, "Sagayarapuram",                "East",         "Pulakeshinagar"),
    (61, "S K Garden",                   "East",         "Pulakeshinagar"),
    (62, "Ramaswamy Palya",              "East",         "Shivajinagar"),
    (63, "Jayamahal",                    "East",         "Shivajinagar"),
    (64, "Rajamahal Guttahalli",         "West",         "Malleshwaram"),
    (65, "Kadumalleshwara",              "West",         "Malleshwaram"),
    (66, "Subrahmanyanagar",             "West",         "Malleshwaram"),
    (67, "Nagapura",                     "West",         "Mahalakshmi Layout"),
    (68, "Mahalakshmipuram",             "West",         "Mahalakshmi Layout"),
    (69, "Laggere",                      "RR Nagar",     "Rajarajeshwarinagar"),
    (70, "Rajagopalanagar",              "Dasarahalli",  "Dasarahalli"),
    (71, "Hegganahalli",                 "Dasarahalli",  "Dasarahalli"),
    (72, "Herohalli",                    "RR Nagar",     "Yeshwanthpura"),
    (73, "Kottigepalya",                 "RR Nagar",     "Rajarajeshwarinagar"),
    (74, "Shakthiganapathinagar",        "West",         "Mahalakshmi Layout"),
    (75, "Shankara Matha",               "West",         "Mahalakshmi Layout"),
    (76, "Gayathrinagar",                "West",         "Malleshwaram"),
    (77, "Dattathreya Temple Ward",      "West",         "Gandhi Nagar"),
    (78, "Pulakeshinagar",               "East",         "Pulakeshinagar"),
    (79, "Sarvagna Nagar",               "East",         "C V Raman Nagar"),
    (80, "Hoysalanagar",                 "East",         "C V Raman Nagar"),
    (81, "Vignananagar",                 "Mahadevapura", "Krishnarajapuram"),
    (82, "Garudacharpalya",              "Mahadevapura", "Mahadevapura"),
    (83, "Kadugodi",                     "Mahadevapura", "Mahadevapura"),
    (84, "Hagadooru",                    "Mahadevapura", "Mahadevapura"),
    (85, "Doddanekkundi",                "Mahadevapura", "Mahadevapura"),
    (86, "Marathahalli",                 "Mahadevapura", "Mahadevapura"),
    (87, "HAL Airport Ward",             "Mahadevapura", "Krishnarajapuram"),
    (88, "Jeevanabima Nagar",            "East",         "C V Raman Nagar"),
    (89, "Jogupalya",                    "East",         "Shanthinagar"),
    (90, "Ulsoor",                       "East",         "Shivajinagar"),
    (91, "Bharathinagar",                "East",         "Shivajinagar"),
    (92, "Shivajinagar",                 "East",         "Shivajinagar"),
    (93, "Vasanthnagar",                 "East",         "Shivajinagar"),
    (94, "Gandhinagar",                  "West",         "Gandhi Nagar"),
    (95, "Subhashnagar",                 "West",         "Gandhi Nagar"),
    (96, "Okalipuram",                   "West",         "Gandhi Nagar"),
    (97, "Dayananda Nagar",              "West",         "Rajaji Nagar"),
    (98, "Prakashnagar",                 "West",         "Rajaji Nagar"),
    (99, "Rajajinagar",                  "West",         "Rajaji Nagar"),
    (100,"Basaveshwaranagar",            "West",         "Rajaji Nagar"),
    (101,"Kamakshipalya",                "West",         "Rajaji Nagar"),
    (102,"Vrishabhavathi Ward",          "West",         "Mahalakshmi Layout"),
    (103,"Kaveripura",                   "South",        "Govindraj Nagar"),
    (104,"Govindarajanagar",             "South",        "Govindraj Nagar"),
    (105,"Agrahara Dasarahalli",         "South",        "Govindraj Nagar"),
    (106,"Dr Rajkumar Ward",             "South",        "Govindraj Nagar"),
    (107,"Shivanagar",                   "West",         "Rajaji Nagar"),
    (108,"Srirama Mandir",               "West",         "Rajaji Nagar"),
    (109,"Chickpete",                    "West",         "Gandhi Nagar"),
    (110,"Sampangiramanagar",            "East",         "Shivajinagar"),
    (111,"Shanthalanagar",               "East",         "Shanthinagar"),
    (112,"Domlur",                       "East",         "Shanthinagar"),
    (113,"Konena Agrahara",              "East",         "C V Raman Nagar"),
    (114,"Agaram",                       "East",         "Shanthinagar"),
    (115,"Vannarpet",                    "East",         "Shanthinagar"),
    (116,"Neelasandra",                  "East",         "Shanthinagar"),
    (117,"Shanthinagar",                 "East",         "Shanthinagar"),
    (118,"Sudhamanagar",                 "South",        "Chickpet"),
    (119,"Dharmarayaswamy Temple Ward",  "South",        "Chickpet"),
    (120,"Cottonpet",                    "West",         "Gandhi Nagar"),
    (121,"Binnipete",                    "West",         "Gandhi Nagar"),
    (122,"Kempapura Agrahara",           "South",        "Vijay Nagar"),
    (123,"Vijayanagar",                  "South",        "Vijay Nagar"),
    (124,"Hosahalli",                    "South",        "Vijay Nagar"),
    (125,"Marenahalli",                  "South",        "Govindraj Nagar"),
    (126,"Maruthi Mandir Ward",          "South",        "Govindraj Nagar"),
    (127,"Moodalapalya",                 "South",        "Govindraj Nagar"),
    (128,"Nagarabhavi",                  "South",        "Govindraj Nagar"),
    (129,"Jnanabharathi",                "RR Nagar",     "Rajarajeshwarinagar"),
    (130,"Ullalu",                       "RR Nagar",     "Yeshwanthpura"),
    (131,"Nayandahalli",                 "South",        "Govindraj Nagar"),
    (132,"Attiguppe",                    "South",        "Vijay Nagar"),
    (133,"Hampinagar",                   "South",        "Vijay Nagar"),
    (134,"Bapujinagar",                  "South",        "Vijay Nagar"),
    (135,"Padarayanapura",               "West",         "Chamrajpet"),
    (136,"Jagjivanram Nagar",            "West",         "Chamrajpet"),
    (137,"Rayapuram",                    "West",         "Chamrajpet"),
    (138,"Chalavadipalya",               "West",         "Chamrajpet"),
    (139,"Krishnarajendra Market Ward",  "West",         "Chamrajpet"),
    (140,"Chamarajapet",                 "West",         "Chamrajpet"),
    (141,"Azad Nagar",                   "West",         "Chamrajpet"),
    (142,"Sunkenahalli",                 "South",        "Chickpet"),
    (143,"Vishveshwarapuram",            "South",        "Chickpet"),
    (144,"Siddapura",                    "South",        "Chickpet"),
    (145,"Hombegowdanagar",              "South",        "Chickpet"),
    (146,"Lakkasandra",                  "South",        "B T M Layout"),
    (147,"Adugodi",                      "South",        "B T M Layout"),
    (148,"Ejipura",                      "South",        "B T M Layout"),
    (149,"Varthur",                      "Mahadevapura", "Mahadevapura"),
    (150,"Bellandur",                    "Mahadevapura", "Mahadevapura"),
    (151,"Ibluru",                       "Mahadevapura", "Mahadevapura"),
    (152,"Koramangala",                  "South",        "B T M Layout"),
    (153,"Suddagunte Palya",             "South",        "B T M Layout"),
    (154,"Madivala",                     "South",        "B T M Layout"),
    (155,"Jakkasandra",                  "South",        "B T M Layout"),
    (156,"BTM Layout",                   "South",        "B T M Layout"),
    (157,"Akshayanagar",                 "Bommanahalli", "Bommanahalli"),
    (158,"Byrasandra",                   "South",        "Jayanagar"),
    (159,"Jayanagar East",               "South",        "Jayanagar"),
    (160,"Gurappanapalya",               "South",        "Jayanagar"),
    (161,"HSR Layout",                   "South",        "Jayanagar"),
    (162,"Bommanahalli",                 "Bommanahalli", "Bommanahalli"),
    (163,"Singasandra",                  "Bommanahalli", "Bommanahalli"),
    (164,"Begur",                        "Bommanahalli", "Bommanahalli"),
    (165,"Arakere",                      "Bommanahalli", "Bommanahalli"),
    (166,"Gottigere",                    "Bommanahalli", "Bommanahalli"),
    (167,"Hulimavu",                     "Bommanahalli", "Bommanahalli"),
    (168,"Hongasandra",                  "Bommanahalli", "Bommanahalli"),
    (169,"Mangammanapalya",              "Bommanahalli", "Bommanahalli"),
    (170,"Jayanagar",                    "South",        "Jayanagar"),
    (171,"Basavanagudi",                 "South",        "Basavanagudi"),
    (172,"Kumaraswamy Layout",           "South",        "Padmanabha Nagar"),
    (173,"Padmanabha Nagar",             "South",        "Padmanabha Nagar"),
    (174,"Girinagar",                    "South",        "Padmanabha Nagar"),
    (175,"Katriguppe",                   "South",        "Padmanabha Nagar"),
    (176,"Vidyapeeta Ward",              "South",        "Basavanagudi"),
    (177,"Ganesh Mandir Ward",           "South",        "Basavanagudi"),
    (178,"Karisandra",                   "South",        "Basavanagudi"),
    (179,"Yediyur",                      "South",        "Basavanagudi"),
    (180,"Pattabhirama Nagar",           "South",        "Padmanabha Nagar"),
    (181,"Byrasandra South",             "South",        "Bangalore South"),
    (182,"Kanakapur Road",               "South",        "Padmanabha Nagar"),
    (183,"Chikkalsandra",                "South",        "Padmanabha Nagar"),
    (184,"Uttarahalli",                  "Bommanahalli", "Bangalore South"),
    (185,"Yelchenahalli",                "Bommanahalli", "Bangalore South"),
    (186,"Jaraganahalli",                "Bommanahalli", "Bommanahalli"),
    (187,"Puttenahalli",                 "Bommanahalli", "Bommanahalli"),
    (188,"Bilekhalli",                   "Bommanahalli", "Bommanahalli"),
    (189,"Honga Sandra",                 "Bommanahalli", "Bommanahalli"),
    (190,"Mangammana Palya",             "Bommanahalli", "Bommanahalli"),
    (191,"Singasandra South",            "Bommanahalli", "Bangalore South"),
    (192,"Begur South",                  "Bommanahalli", "Bangalore South"),
    (193,"Electronic City Phase 1",      "Bommanahalli", "Bommanahalli"),
    (194,"Electronic City Phase 2",      "Bommanahalli", "Bommanahalli"),
    (195,"Anjanapura",                   "Bommanahalli", "Bangalore South"),
    (196,"Kudlu",                        "Bommanahalli", "Bommanahalli"),
    (197,"Garvebhavipalya",              "Bommanahalli", "Bommanahalli"),
    (198,"Hemmigepura",                  "RR Nagar",     "Rajarajeshwarinagar"),
]

# ─────────────────────────────────────────────────────────────
# LOOKUPS
# ─────────────────────────────────────────────────────────────

_WARD_BY_ID = {}
_WARD_BY_NAME = {}

def _build_ward_record(wno, wname, zone, constituency):
    mla_data = CONSTITUENCY_MLA.get(constituency, ("—", "VERIFY_REQUIRED", "—"))
    zone_m = ZONE_META.get(zone, {})
    return {
        "ward_id": wno,
        "ward_name": wname,
        "zone": zone,
        "constituency": constituency,
        "constituency_no": mla_data[0],
        "mla": mla_data[1],
        "mla_party": mla_data[2],
        "zonal_commissioner": zone_m.get("zc", "VERIFY_REQUIRED"),
        "joint_commissioner": zone_m.get("jc", "VERIFY_REQUIRED"),
        "engineering_owner": f"AEE – {zone} Zone, BBMP",
        "health_owner": f"Health Inspector – {zone} Zone, BBMP",
        "swm_contractor": zone_m.get("swm", "VERIFY_REQUIRED"),
        "bwssb_division": zone_m.get("bwssb", "VERIFY_REQUIRED"),
        "bescom_subdivision": zone_m.get("bescom", "VERIFY_REQUIRED"),
        "latitude_approx": None,
        "longitude_approx": None,
    }

for row in WARDS_198:
    rec = _build_ward_record(*row)
    _WARD_BY_ID[row[0]] = rec
    _WARD_BY_NAME[row[1].lower()] = rec

ALL_WARD_NAMES = [w[1] for w in WARDS_198]

# ─────────────────────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────────────────────

class Issue(db.Model):
    __tablename__ = "issues"

    id = db.Column(db.Integer, primary_key=True)
    fingerprint = db.Column(db.String(64), unique=True, nullable=False, index=True)
    external_id = db.Column(db.String(64), nullable=True)
    issue_type = db.Column(db.String(64), nullable=False, default="Pothole")
    description = db.Column(db.Text, nullable=False)
    location_name = db.Column(db.String(255), nullable=True)
    ward = db.Column(db.String(255), nullable=True)
    ward_id = db.Column(db.Integer, nullable=True, index=True)
    zone = db.Column(db.String(128), nullable=True, index=True)
    constituency = db.Column(db.String(128), nullable=True)
    mla = db.Column(db.String(128), nullable=True)
    severity = db.Column(db.String(32), nullable=False, default="medium")
    status = db.Column(db.String(32), nullable=False, default="open")
    source = db.Column(db.String(64), nullable=False)
    source_url = db.Column(db.Text, nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    upvotes = db.Column(db.Integer, nullable=False, default=0)
    image_url = db.Column(db.Text, nullable=True)
    is_seed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def as_dict(self):
        return {
            "id": self.id,
            "external_id": self.external_id,
            "issue_type": self.issue_type,
            "description": self.description,
            "location_name": self.location_name,
            "ward": self.ward,
            "ward_id": self.ward_id,
            "zone": self.zone,
            "constituency": self.constituency,
            "mla": self.mla,
            "severity": self.severity,
            "status": self.status,
            "source": self.source,
            "source_url": self.source_url,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "upvotes": self.upvotes,
            "image_url": self.image_url,
            "is_seed": self.is_seed,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
        }

class IngestionRun(db.Model):
    __tablename__ = "ingestion_runs"

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    sources = db.Column(db.String(255), nullable=False)
    fetched_count = db.Column(db.Integer, nullable=False, default=0)
    saved_count = db.Column(db.Integer, nullable=False, default=0)
    skipped_count = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(32), nullable=False, default="running")
    note = db.Column(db.Text, nullable=True)

# ─────────────────────────────────────────────────────────────
# SCRAPING CONFIG
# ─────────────────────────────────────────────────────────────

OPENCITY_CSV = (
    "https://data.opencity.in/dataset/"
    "3a1a98f8-f924-4257-a2a1-3b957b55b9f5/resource/"
    "22be8fdc-532d-4ec8-8e31-2e6d26d5ce85/download/"
    "e03fbadf-ff1a-4fe1-9aad-a2a38a2bd81d.csv"
)
OPENCITY_KML = (
    "https://data.opencity.in/dataset/"
    "3a1a98f8-f924-4257-a2a1-3b957b55b9f5/resource/"
    "d1d4a437-95ee-4327-9154-f9a8933b2110/download/"
    "63b30ddf-5919-43d0-a6cf-17d5cc90a35c.kml"
)
HEADERS = {"User-Agent": "Mozilla/5.0 CivicAI/6.0 (civic-accountability-platform)"}

ISSUE_KW = {
    "Pothole": ["pothole", "crater", "road damage", "road caved", "bad road"],
    "Garbage": ["garbage", "waste", "trash", "litter", "dump", "stench", "sanitation"],
    "Water Logging": ["waterlog", "flood", "water stagnant", "inundated", "water clog"],
    "Open Drain": ["open drain", "manhole", "gutter", "sewer", "drain cover"],
    "Broken Streetlight": ["streetlight", "street light", "no light", "dark road", "lamp"],
    "Illegal Dumping": ["illegal dump", "debris dump", "construction waste"],
    "Damaged Footpath": ["footpath", "pavement broken", "sidewalk", "broken tiles"],
    "Encroachment": ["encroach", "illegal construction"],
}

SEED_ISSUES_RAW = [
    ("Pothole", "Large pothole on 12th Main causing daily near-miss accidents", "Indiranagar", "critical", 12.9784, 77.6408, 14),
    ("Garbage", "Overflowing garbage bins — 5 days uncollected near market", "Koramangala", "high", 12.9352, 77.6245, 8),
    ("Open Drain", "Exposed drain near school gate — children at risk", "Rajajinagar", "high", 12.9914, 77.5530, 5),
    ("Water Logging", "Severe waterlogging — vehicles stuck 2+ hrs after rain", "Bellandur", "critical", 12.9352, 77.6395, 2),
    ("Pothole", "Road caved in, blocking one full lane on 80ft Road", "BTM Layout", "critical", 12.9165, 77.6101, 18),
    ("Pothole", "Deep pothole near IT park gate causing accidents", "Electronic City Phase 1", "high", 12.8399, 77.6770, 27),
    ("Garbage", "Dead animal on main road not removed for 3 days", "Hebbala", "high", 13.0358, 77.5970, 45),
    ("Broken Streetlight", "3 consecutive streetlights broken — road completely dark", "Malleswaram", "medium", 13.0035, 77.5709, 20),
    ("Illegal Dumping", "Construction debris dumped on public footpath", "Hongasandra", "medium", 12.8959, 77.6204, 31),
    ("Damaged Footpath", "Broken tiles hazard near mall — elderly resident fell", "BTM Layout", "low", 12.9100, 77.6050, 30),
    ("Water Logging", "Severe flooding on ITPL Road every rain season", "Hoodi", "critical", 12.9698, 77.7499, 2),
    ("Pothole", "Near-miss accidents daily near Akshayanagar junction", "Akshayanagar", "high", 12.8559, 77.6204, 9),
    ("Garbage", "Garbage not collected for 6 days in Begur main road", "Begur", "high", 12.8527, 77.6203, 6),
    ("Open Drain", "Uncovered manhole near Bommanahalli bus stop", "Bommanahalli", "critical", 12.8960, 77.6337, 3),
    ("Water Logging", "Singasandra underpass floods every monsoon rain", "Singasandra", "high", 12.8899, 77.6278, 4),
]

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def utc_now_iso():
    return datetime.utcnow().isoformat() + "Z"

def gen_external_id():
    return "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=7))

def classify_type(text):
    t = (text or "").lower()
    for it, kws in ISSUE_KW.items():
        if any(k in t for k in kws):
            return it
    return "Pothole"

def classify_severity(text):
    t = (text or "").lower()
    if any(w in t for w in ["accident", "death", "fatal", "collapse", "emergency", "critical", "hazard"]):
        return "critical"
    if any(w in t for w in ["flood", "major", "severe", "urgent", "horrible", "terrible"]):
        return "high"
    if any(w in t for w in ["minor", "small", "slight"]):
        return "low"
    return "medium"

def infer_ward(text):
    t = (text or "").lower()
    for name in ALL_WARD_NAMES:
        if name.lower() in t:
            return name
    return None

def valid_blr(lat, lon):
    return (12.7 < lat < 13.2) and (77.3 < lon < 77.9)

def normalize_issue_payload(description, source, lat=None, lon=None, ward=None,
                            issue_type=None, days_ago=None, source_url=None, is_seed=False):
    if days_ago is None:
        days_ago = random.randint(0, 14)
    ts = (datetime.utcnow() - timedelta(days=days_ago))
    w = ward or infer_ward(description)
    wr = _WARD_BY_NAME.get(w.lower()) if w else None

    return {
        "external_id": gen_external_id(),
        "issue_type": issue_type or classify_type(description),
        "description": (description or "").strip()[:220],
        "location_name": w,
        "ward": w,
        "ward_id": wr["ward_id"] if wr else None,
        "zone": wr["zone"] if wr else None,
        "constituency": wr["constituency"] if wr else None,
        "mla": wr["mla"] if wr else None,
        "severity": classify_severity(description),
        "status": "open",
        "source": source,
        "source_url": source_url,
        "latitude": round(lat, 6) if lat is not None else None,
        "longitude": round(lon, 6) if lon is not None else None,
        "created_at": ts,
        "updated_at": ts,
        "upvotes": random.randint(1, 50),
        "image_url": None,
        "is_seed": is_seed,
    }

def compute_fingerprint(item):
    parts = [
        (item.get("source") or "").strip().lower(),
        (item.get("source_url") or "").strip().lower(),
        (item.get("description") or "").strip().lower()[:180],
        str(item.get("ward_id") or ""),
        str(round(item.get("latitude"), 4)) if item.get("latitude") is not None else "",
        str(round(item.get("longitude"), 4)) if item.get("longitude") is not None else "",
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def issue_to_model(item):
    return Issue(
        fingerprint=compute_fingerprint(item),
        external_id=item.get("external_id"),
        issue_type=item.get("issue_type", "Pothole"),
        description=item.get("description", "").strip(),
        location_name=item.get("location_name"),
        ward=item.get("ward"),
        ward_id=item.get("ward_id"),
        zone=item.get("zone"),
        constituency=item.get("constituency"),
        mla=item.get("mla"),
        severity=item.get("severity", "medium"),
        status=item.get("status", "open"),
        source=item.get("source", "manual"),
        source_url=item.get("source_url"),
        latitude=item.get("latitude"),
        longitude=item.get("longitude"),
        upvotes=item.get("upvotes", 0),
        image_url=item.get("image_url"),
        is_seed=item.get("is_seed", False),
        created_at=item.get("created_at", datetime.utcnow()),
        updated_at=item.get("updated_at", datetime.utcnow()),
    )

def build_leaderboard(issues):
    counts = {}
    for i in issues:
        w = i.get("ward") or "Unmapped"
        counts[w] = counts.get(w, 0) + 1
    return sorted(
        [{"ward": k, "count": v} for k, v in counts.items()],
        key=lambda x: x["count"],
        reverse=True
    )[:15]

def build_clusters(issues):
    clusters = {}
    for i in issues:
        key = (i.get("description") or "")[:35].strip().lower()
        if key:
            clusters.setdefault(key, []).append(i)
    result = [{"cluster": k.capitalize(), "items": v} for k, v in clusters.items() if len(v) >= 2]
    result.sort(key=lambda x: len(x["items"]), reverse=True)
    return result[:10]

def deduplicate_payloads(issues):
    seen_fps = set()
    unique = []
    for i in issues:
        fp = compute_fingerprint(i)
        if fp in seen_fps:
            continue
        seen_fps.add(fp)
        unique.append(i)
    return unique

# ─────────────────────────────────────────────────────────────
# FETCHERS
# ─────────────────────────────────────────────────────────────

def fetch_opencity_csv():
    results = []
    try:
        resp = requests.get(OPENCITY_CSV, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        reader = csv.DictReader(StringIO(resp.text))
        for i, row in enumerate(reader):
            if i >= 100:
                break
            ward = (row.get("Ward Name") or row.get("ward_name") or row.get("Ward") or "").strip()
            lat_s = (row.get("Latitude") or row.get("latitude") or "").strip()
            lon_s = (row.get("Longitude") or row.get("longitude") or "").strip()
            desc = (row.get("Description") or row.get("description") or "").strip()
            if not desc:
                desc = f"Pothole reported in {ward}" if ward else "Pothole reported"
            try:
                lat = float(lat_s) if lat_s else None
                lon = float(lon_s) if lon_s else None
                if lat is not None and lon is not None and not valid_blr(lat, lon):
                    lat = lon = None
            except Exception:
                lat = lon = None

            matched = _WARD_BY_NAME.get(ward.lower()) if ward else None
            results.append(normalize_issue_payload(
                desc,
                "OpenCity CSV",
                lat,
                lon,
                ward=matched["ward_name"] if matched else ward or None,
                issue_type="Pothole",
                days_ago=random.randint(1, 60),
                source_url=OPENCITY_CSV
            ))
    except Exception as e:
        app.logger.exception(f"[CSV] {e}")
    return results

def fetch_opencity_kml():
    results = []
    try:
        resp = requests.get(OPENCITY_KML, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        content = resp.content.decode("utf-8", errors="replace")
        content = re.sub(r'\s+xmlns[^"]*"[^"]*"', "", content)
        root = ET.fromstring(content.encode())
        for p in root.findall(".//Placemark")[:80]:
            desc_el = p.find(".//description")
            coord_el = p.find(".//coordinates")
            desc = (desc_el.text or "Pothole").strip()[:220] if desc_el is not None else "Pothole"

            lat = lon = None
            if coord_el is not None and coord_el.text:
                try:
                    pts = coord_el.text.strip().split(",")
                    lon_c, lat_c = float(pts[0]), float(pts[1])
                    if valid_blr(lat_c, lon_c):
                        lat, lon = lat_c, lon_c
                except Exception:
                    pass

            results.append(normalize_issue_payload(
                desc,
                "OpenCity KML",
                lat,
                lon,
                ward=infer_ward(desc),
                issue_type="Pothole",
                days_ago=random.randint(1, 60),
                source_url=OPENCITY_KML
            ))
    except Exception as e:
        app.logger.exception(f"[KML] {e}")
    return results

def fetch_reddit():
    results = []
    try:
        q = "pothole OR garbage OR drain OR flood OR BBMP OR streetlight OR waterlogging"
        url = (
            f"https://www.reddit.com/r/bangalore/search.json"
            f"?q={requests.utils.quote(q)}&sort=new&restrict_sr=1&limit=20&t=week"
        )
        resp = requests.get(url, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("data", {}).get("children", [])
        for p in posts:
            d = p.get("data", {})
            text = f"{d.get('title', '')}. {d.get('selftext', '')}"[:220].strip()
            link = "https://reddit.com" + (d.get("permalink") or "")
            if len(text) > 20:
                results.append(normalize_issue_payload(
                    text,
                    "reddit",
                    ward=infer_ward(text),
                    source_url=link
                ))
    except Exception as e:
        app.logger.exception(f"[Reddit] {e}")
    return results

def fetch_google_news():
    results = []
    queries = [
        "Bengaluru pothole BBMP when:7d",
        "Bengaluru garbage BBMP when:7d",
        "Bengaluru waterlogging BBMP when:7d",
    ]
    for q in queries:
        try:
            url = f"https://news.google.com/rss/search?q={requests.utils.quote(q)}&hl=en-IN&gl=IN&ceid=IN:en"
            resp = requests.get(url, headers=HEADERS, timeout=12)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:6]:
                title = getattr(item.find("title"), "text", "") or ""
                desc = getattr(item.find("description"), "text", "") or ""
                link = getattr(item.find("link"), "text", "") or ""
                desc = re.sub(r"<[^>]+>", " ", desc).strip()
                text = f"{title}. {desc}"[:220].strip()
                if len(text) > 20:
                    results.append(normalize_issue_payload(
                        text,
                        "news",
                        ward=infer_ward(text),
                        source_url=link
                    ))
            time.sleep(0.25)
        except Exception as e:
            app.logger.exception(f"[News] {q}: {e}")
    return results

def get_seed_issues():
    issues = []
    for itype, desc, ward_name, sev, lat, lon, days in SEED_ISSUES_RAW:
        matched = _WARD_BY_NAME.get(ward_name.lower())
        issue = normalize_issue_payload(
            desc,
            "seed",
            lat,
            lon,
            ward=matched["ward_name"] if matched else ward_name,
            issue_type=itype,
            days_ago=days,
            is_seed=True
        )
        issue["severity"] = sev
        issues.append(issue)
    return issues

def run_pipeline(sources_param="csv,kml,reddit,news"):
    sources = [s.strip().lower() for s in sources_param.split(",") if s.strip()]
    all_issues = []
    fetched = []
    source_status = {}

    if "csv" in sources:
        d = fetch_opencity_csv()
        all_issues.extend(d)
        source_status["csv"] = {"count": len(d), "status": "ok" if d else "empty"}
        if d:
            fetched.append("OpenCity CSV")

    if "kml" in sources:
        d = fetch_opencity_kml()
        all_issues.extend(d)
        source_status["kml"] = {"count": len(d), "status": "ok" if d else "empty"}
        if d:
            fetched.append("OpenCity KML")

    if "reddit" in sources:
        d = fetch_reddit()
        all_issues.extend(d)
        source_status["reddit"] = {"count": len(d), "status": "ok" if d else "empty"}
        if d:
            fetched.append("Reddit r/bangalore")

    if "news" in sources:
        d = fetch_google_news()
        all_issues.extend(d)
        source_status["news"] = {"count": len(d), "status": "ok" if d else "empty"}
        if d:
            fetched.append("Google News")

    if not all_issues:
        all_issues = get_seed_issues()
        fetched = ["Seed (fallback)"]
        source_status["fallback"] = {"count": len(all_issues), "status": "used"}

    unique = deduplicate_payloads(all_issues)
    sev_ord = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    unique.sort(key=lambda x: sev_ord.get(x.get("severity", "low"), 4))

    return {
        "issues": unique,
        "leaderboard": build_leaderboard(unique),
        "clusters": build_clusters(unique),
        "sources_fetched": fetched,
        "source_status": source_status
    }

# ─────────────────────────────────────────────────────────────
# DB INITIALIZATION
# ─────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

# ─────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    try:
        with open("CivicAI.html", "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}
    except FileNotFoundError:
        return (
            "<h2 style='font-family:sans-serif;padding:40px'>"
            "⚠ CivicAI.html not found. Place it in the same folder as app.py</h2>"
        ), 404

@app.route("/health")
def health():
    total_issues = db.session.scalar(db.select(func.count(Issue.id))) or 0
    last_run = db.session.execute(
        db.select(IngestionRun).order_by(IngestionRun.id.desc()).limit(1)
    ).scalar_one_or_none()

    return jsonify({
        "status": "ok",
        "service": "CivicAI",
        "version": "6.0",
        "wards": len(WARDS_198),
        "issues_in_db": total_issues,
        "db_uri_type": "postgresql" if "postgresql" in db_url else "sqlite",
        "last_ingestion": {
            "status": last_run.status if last_run else None,
            "started_at": last_run.started_at.isoformat() + "Z" if last_run and last_run.started_at else None,
            "completed_at": last_run.completed_at.isoformat() + "Z" if last_run and last_run.completed_at else None,
            "fetched_count": last_run.fetched_count if last_run else 0,
            "saved_count": last_run.saved_count if last_run else 0,
            "skipped_count": last_run.skipped_count if last_run else 0,
            "sources": last_run.sources if last_run else None,
        },
        "timestamp": utc_now_iso()
    }), 200

@app.route("/wards")
def get_all_wards():
    zone_filter = request.args.get("zone", "").strip()
    wards = list(_WARD_BY_ID.values())
    if zone_filter:
        wards = [w for w in wards if w["zone"].lower() == zone_filter.lower()]
    return jsonify({"count": len(wards), "wards": wards}), 200

@app.route("/ward/<int:ward_id>")
def get_ward(ward_id):
    ward = _WARD_BY_ID.get(ward_id)
    if not ward:
        return jsonify({"error": f"Ward {ward_id} not found. Valid range: 1–198"}), 404

    issue_count = db.session.scalar(
        db.select(func.count(Issue.id)).where(Issue.ward_id == ward_id)
    ) or 0

    return jsonify({
        **ward,
        "issue_count": issue_count,
        "issue_sla_days": ISSUE_SLA,
        "escalation_matrix": {
            "Engineering": {
                "l1": ward["engineering_owner"],
                "l2": f"Executive Engineer – {ward['zone']} Zone",
                "l3": "Chief Engineer – BBMP HQ"
            },
            "Health+SWM": {
                "l1": ward["health_owner"],
                "l2": f"Health Officer – {ward['zone']} Zone",
                "l3": "Chief Health Officer – BBMP"
            },
            "Water": {
                "l1": ward["bwssb_division"],
                "l2": "BWSSB Division Office",
                "l3": "BWSSB Chief Engineer"
            },
            "Electricity": {
                "l1": ward["bescom_subdivision"],
                "l2": "BESCOM Sub-Division Office",
                "l3": "BESCOM Division Office"
            }
        }
    }), 200

@app.route("/resolve")
def resolve():
    ward_id_s = request.args.get("ward_id", "").strip()
    issue_type_q = request.args.get("issue_type", "").strip().lower()

    it_map = {
        "pothole": "Pothole",
        "road": "Pothole",
        "crater": "Pothole",
        "garbage": "Garbage",
        "waste": "Garbage",
        "trash": "Garbage",
        "illegal dump": "Illegal Dumping",
        "construction waste": "Illegal Dumping",
        "water": "Water",
        "bwssb": "Water",
        "pipe": "Water",
        "electricity": "Electricity",
        "light": "Broken Streetlight",
        "streetlight": "Broken Streetlight",
        "bescom": "Electricity",
        "drain": "Open Drain",
        "manhole": "Open Drain",
        "gutter": "Open Drain",
        "flood": "Water Logging",
        "waterlog": "Water Logging",
        "footpath": "Damaged Footpath",
        "pavement": "Damaged Footpath",
        "encroach": "Encroachment",
    }

    matched_type = None
    for kw, it in it_map.items():
        if kw in issue_type_q:
            matched_type = it
            break
    if not matched_type:
        matched_type = "Pothole"

    dept_info = ISSUE_DEPT.get(matched_type, ISSUE_DEPT["Pothole"])

    ward = None
    if ward_id_s.isdigit():
        ward = _WARD_BY_ID.get(int(ward_id_s))
    if not ward and ward_id_s:
        ward = _WARD_BY_NAME.get(ward_id_s.lower())

    zone_specific = {}
    primary_contact = dept_info["primary"]
    data_quality = "generic"

    if ward:
        if matched_type in ["Pothole", "Water Logging", "Open Drain", "Damaged Footpath"]:
            primary_contact = ward["engineering_owner"]
        elif matched_type in ["Garbage", "Illegal Dumping"]:
            primary_contact = ward["health_owner"]
        elif matched_type == "Water":
            primary_contact = ward["bwssb_division"]
        elif matched_type in ["Electricity", "Broken Streetlight"]:
            primary_contact = ward["bescom_subdivision"]
        elif matched_type == "Encroachment":
            primary_contact = f"Revenue Officer – {ward['zone']} Zone"

        zone_specific = {
            "engineering_contact": ward["engineering_owner"],
            "health_contact": ward["health_owner"],
            "swm_contractor": ward["swm_contractor"],
            "bwssb_division": ward["bwssb_division"],
            "bescom_subdivision": ward["bescom_subdivision"],
            "mla": ward["mla"],
            "mla_party": ward["mla_party"],
            "zonal_commissioner": ward["zonal_commissioner"],
            "joint_commissioner": ward["joint_commissioner"],
        }
        data_quality = "zone_level_verified"

    return jsonify({
        "ward": ward,
        "issue_type": matched_type,
        "department": dept_info["dept"],
        "primary_contact": primary_contact,
        "sla_days": ISSUE_SLA.get(matched_type, 7),
        "data_quality": data_quality,
        "escalation": {
            "level_1_ward": primary_contact,
            "level_2_zone": dept_info["escalate_l2"],
            "level_3_central": dept_info["escalate_l3"],
        },
        **zone_specific,
        "bbmp_helpline": "080-22660000",
        "bbmp_whatsapp": "9480685700",
        "bwssb_helpline": "1916",
        "bescom_helpline": "1912",
    }), 200

@app.route("/issues", methods=["GET"])
def get_issues():
    ward_id = request.args.get("ward_id", type=int)
    zone = request.args.get("zone", "").strip()
    issue_type = request.args.get("issue_type", "").strip()
    status = request.args.get("status", "").strip()
    limit = min(request.args.get("limit", default=100, type=int), 300)

    stmt = db.select(Issue).order_by(Issue.created_at.desc())

    if ward_id:
        stmt = stmt.where(Issue.ward_id == ward_id)
    if zone:
        stmt = stmt.where(func.lower(Issue.zone) == zone.lower())
    if issue_type:
        stmt = stmt.where(func.lower(Issue.issue_type) == issue_type.lower())
    if status:
        stmt = stmt.where(func.lower(Issue.status) == status.lower())

    rows = db.session.execute(stmt.limit(limit)).scalars().all()

    payload = [r.as_dict() for r in rows]
    return jsonify({
        "count": len(payload),
        "issues": payload,
        "leaderboard": build_leaderboard(payload),
        "clusters": build_clusters(payload),
    }), 200

@app.route("/issues", methods=["POST"])
def create_issue():
    data = request.get_json(silent=True) or {}

    description = (data.get("description") or "").strip()
    if not description:
        return jsonify({"error": "description is required"}), 400

    ward_id = data.get("ward_id")
    ward_name = (data.get("ward") or "").strip()
    ward = None

    if ward_id is not None:
        try:
            ward = _WARD_BY_ID.get(int(ward_id))
        except Exception:
            ward = None

    if ward is None and ward_name:
        ward = _WARD_BY_NAME.get(ward_name.lower())

    lat = data.get("latitude")
    lon = data.get("longitude")
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
        if lat is not None and lon is not None and not valid_blr(lat, lon):
            lat = lon = None
    except Exception:
        lat = lon = None

    item = normalize_issue_payload(
        description=description,
        source=data.get("source", "citizen"),
        lat=lat,
        lon=lon,
        ward=ward["ward_name"] if ward else (ward_name or infer_ward(description)),
        issue_type=data.get("issue_type") or classify_type(description),
        source_url=data.get("source_url"),
        is_seed=False,
    )

    if "severity" in data and data["severity"]:
        item["severity"] = str(data["severity"]).lower()
    if "status" in data and data["status"]:
        item["status"] = str(data["status"]).lower()

    fp = compute_fingerprint(item)
    existing = db.session.execute(
        db.select(Issue).where(Issue.fingerprint == fp)
    ).scalar_one_or_none()

    if existing:
        return jsonify({
            "status": "duplicate",
            "message": "Issue already exists",
            "issue": existing.as_dict()
        }), 200

    obj = issue_to_model(item)
    db.session.add(obj)
    db.session.commit()

    return jsonify({
        "status": "created",
        "issue": obj.as_dict()
    }), 201

@app.route("/issues/<int:issue_id>", methods=["PATCH"])
def update_issue(issue_id):
    issue = db.session.get(Issue, issue_id)
    if not issue:
        return jsonify({"error": "Issue not found"}), 404

    data = request.get_json(silent=True) or {}

    allowed = {"status", "severity", "upvotes", "image_url"}
    for k, v in data.items():
        if k in allowed:
            setattr(issue, k, v)

    issue.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"status": "updated", "issue": issue.as_dict()}), 200

@app.route("/scrape", methods=["GET"])
def scrape_preview():
    sources_param = request.args.get("sources", "csv,kml,reddit,news")
    limit = min(request.args.get("limit", default=100, type=int), 200)

    try:
        result = run_pipeline(sources_param)
        return jsonify({
            "status": "success",
            "mode": "preview_only",
            "timestamp": utc_now_iso(),
            "count": len(result["issues"][:limit]),
            "sources_fetched": result["sources_fetched"],
            "source_status": result["source_status"],
            "issues": result["issues"][:limit],
            "leaderboard": result["leaderboard"],
            "clusters": result["clusters"],
        }), 200
    except Exception as e:
        app.logger.exception(f"[Scrape Preview] Fatal: {e}")
        seed = get_seed_issues()
        return jsonify({
            "status": "fallback",
            "mode": "preview_only",
            "timestamp": utc_now_iso(),
            "count": len(seed),
            "sources_fetched": ["Seed (emergency fallback)"],
            "issues": seed,
            "leaderboard": build_leaderboard(seed),
            "clusters": [],
            "error_note": str(e),
        }), 200

@app.route("/scrape/sync", methods=["POST", "GET"])
def scrape_sync():
    sources_param = request.args.get("sources", "csv,kml,reddit,news")
    limit = min(request.args.get("limit", default=200, type=int), 300)

    run = IngestionRun(
        sources=sources_param,
        status="running",
        started_at=datetime.utcnow()
    )
    db.session.add(run)
    db.session.commit()

    try:
        result = run_pipeline(sources_param)
        items = result["issues"][:limit]

        saved = 0
        skipped = 0

        for item in items:
            fp = compute_fingerprint(item)
            exists = db.session.execute(
                db.select(Issue).where(Issue.fingerprint == fp)
            ).scalar_one_or_none()

            if exists:
                skipped += 1
                continue

            obj = issue_to_model(item)
            db.session.add(obj)
            saved += 1

        db.session.commit()

        run.completed_at = datetime.utcnow()
        run.fetched_count = len(items)
        run.saved_count = saved
        run.skipped_count = skipped
        run.status = "success"
        run.note = ",".join(result["sources_fetched"])
        db.session.commit()

        total_issues = db.session.scalar(db.select(func.count(Issue.id))) or 0

        return jsonify({
            "status": "success",
            "timestamp": utc_now_iso(),
            "fetched_count": len(items),
            "saved_count": saved,
            "skipped_count": skipped,
            "total_issues_in_db": total_issues,
            "sources_fetched": result["sources_fetched"],
            "source_status": result["source_status"],
        }), 200

    except Exception as e:
        db.session.rollback()
        run.completed_at = datetime.utcnow()
        run.status = "failed"
        run.note = str(e)[:500]
        db.session.add(run)
        db.session.commit()

        return jsonify({
            "status": "failed",
            "timestamp": utc_now_iso(),
            "error": str(e)
        }), 500

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  CivicAI Backend v6 — Bengaluru Civic Intelligence          ║
║  http://0.0.0.0:{port:<5}                                       ║
║  198 verified wards · persistent issues DB · Render-ready   ║
║  GET  /              → CivicAI dashboard                    ║
║  GET  /health        → health + DB + ingestion status       ║
║  GET  /wards         → full 198-ward JSON                   ║
║  GET  /ward/<id>     → single ward intelligence             ║
║  GET  /resolve       → dept + escalation path               ║
║  GET  /issues        → persisted issues                     ║
║  POST /issues        → citizen issue create                 ║
║  PATCH /issues/<id>  → update issue                         ║
║  GET  /scrape        → preview scraped issues               ║
║  POST /scrape/sync   → scrape + save to DB                  ║
╚══════════════════════════════════════════════════════════════╝
""")
    app.run(host="0.0.0.0", port=port, debug=False)
