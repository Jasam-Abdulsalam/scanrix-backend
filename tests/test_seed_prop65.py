import csv
import io

from scripts.seed_prop65 import skip_to_table_header

# Mirrors the real OEHHA file: intro paragraphs mention "chemicals" before the real header.
SAMPLE_CSV = '''STATE OF CALIFORNIA,,,,,,,,
PROPOSITION 65 LIST OF CARCINOGENS OR REPRODUCTIVE TOXICANTS,,,,,,,,
"The list of chemicals known to the State to cause cancer or reproductive toxicity.",,,,,,,,
"In the Listing Mechanism column, ""AB"" denotes authoritative bodies.",,,,,,,,
,,,,,,,,
Chemical,Type of Toxicity,Listing Mechanism,CAS No.,Date Listed,NSRL or MADL,,,
Acetaldehyde,cancer,SQE,75-07-0,1-Apr-88,90 (inhalation),,,
Acetamide,cancer ,AB,60-35-5,1-Jan-90,10,,,
'''


def test_skips_intro_rows_and_header():
    reader = csv.reader(io.StringIO(SAMPLE_CSV))
    assert skip_to_table_header(reader) is True
    names = [row[0] for row in reader if row]
    assert names == ["Acetaldehyde", "Acetamide"]


def test_returns_false_when_header_missing():
    reader = csv.reader(io.StringIO("A paragraph about chemicals,,,\nfoo,bar,baz,qux\n"))
    assert skip_to_table_header(reader) is False
