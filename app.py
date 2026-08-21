import io
import re
from lxml import etree
import pandas as pd
from pypdf import PdfReader
import streamlit as st

st.set_page_config(
    page_title="WA State Certified Payroll Tool", layout="wide"
)

st.title("WA State Certified Payroll Tool")

# -------------------------------------------------------------------
# HELPER MAPPINGS & CONSTANTS
# -------------------------------------------------------------------
DAY_MAP = {
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
    "sun": 7
}

KNOWN_PAYROLL_ITEMS = [
    "SN Fridge & AC",
    "Electrical PW Hourly",
    "Plumbing SN",
    "Plumbing SC",
    "Insulation SN",
    "SC Insulation",
    "SC Sheet Metal",
    "Electric Hourly",
    "PW Hourly Electric"
]

# -------------------------------------------------------------------
# FORMATTERS
# -------------------------------------------------------------------
def map_gender(val) -> str:
    if pd.isna(val) or not str(val).strip():
        return "?"
    v = str(val).strip().upper()
    if v.startswith("M"):
        return "M"
    if v.startswith("F"):
        return "F"
    return "?"

def map_veteran(val) -> str:
    if pd.isna(val) or not str(val).strip():
        return "?"
    v = str(val).strip().upper()
    if v.startswith("Y"):
        return "Y"
    if v.startswith("N"):
        return "N"
    return "?"

def format_ssn(val) -> str:
    if pd.isna(val):
        return "000000000"
    digits = "".join(filter(str.isdigit, str(val)))
    if len(digits) == 9:
        return digits
    return "000000000"

def format_rate_or_empty(val) -> str:
    try:
        if pd.isna(val):
            return ""
        num = float(val)
        return f"{num:.2f}" if num > 0 else ""
    except (ValueError, TypeError):
        return ""

def format_benefit_rate(val) -> str:
    try:
        if pd.isna(val) or str(val).strip() in ["", "nan", "None"]:
            return "0.00"
        num = float(val)
        return f"{num:.2f}" if num >= 0 else "0.00"
    except (ValueError, TypeError):
        return "0.00"

def format_hours(val) -> str:
    try:
        if pd.isna(val):
            return "0.0"
        num = float(val)
        return f"{num:.1f}"
    except (ValueError, TypeError):
        return "0.0"

def clean_trade_code(val) -> str:
    return str(val).strip()

def clean_county(val) -> str:
    s = str(val).strip().lower()
    if s.isalpha():
        return s
    return "skagit"

# -------------------------------------------------------------------
# PARSERS (EXCEL & PDF)
# -------------------------------------------------------------------
def parse_excel_to_workbook(uploaded_file) -> dict[str, pd.DataFrame]:
    df = pd.read_excel(uploaded_file)
    
    if 'local_date' in df.columns:
        df['local_date'] = pd.to_datetime(df['local_date']).dt.strftime('%m-%d-%Y')
    else:
        df['local_date'] = "08-13-2026"

    unique_employees = {}
    emp_records = []
    emp_counter = 1
    trades_agg = {}

    for _, row in df.iterrows():
        fname = str(row.get('fname', 'Unknown')).strip()
        lname = str(row.get('lname', 'Worker')).strip()
        date_str = str(row.get('local_date', ''))
        
        day_str = str(row.get('local_day', 'mon')).lower().strip()[:3]
        day_val = DAY_MAP.get(day_str, 1)
        
        hrs = float(row.get('hours', 0.0)) if pd.notna(row.get('hours')) else 0.0
        trade_str = str(row.get('payroll item', 'Unknown Trade')).strip()

        name_key = (fname, lname)
        
        if name_key not in unique_employees:
            emp_id = f"EMP{emp_counter:02d}"
            unique_employees[name_key] = emp_id
            emp_counter += 1

            emp_records.append({
                "Employee ID": emp_id,
                "Intent ID": 1657970,
                "End of Week Date": date_str,
                "No Work Performed (true/false)": False,
                "First Name": fname,
                "Middle Name": "",
                "Last Name": lname,
                "SSN": "",
                "Ethnicity": "Prefer not to answer",
                "Gender": "?",
                "Veteran Status (Y/N/?)": "?",
                "Address 1": "",
                "Address 2": "",
                "City": "",
                "State": "WA",
                "Zip": "",
                "Gross Pay": 0.0,
                "FICA": 0.0,
                "Tax Withholding": 0.0,
            })

        emp_id = unique_employees[name_key]
        trade_key = (emp_id, trade_str)
        
        if trade_key not in trades_agg:
            trades_agg[trade_key] = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0, 7: 0.0}
        
        trades_agg[trade_key][day_val] += hrs

    trades_records = []
    for (emp_id, trade_name), days_dict in trades_agg.items():
        trade_row = {
            "Employee ID": emp_id,
            "Trade": trade_name,
            "Job Class": "Journey Level",
            "Trade Notes": "",
            "County": "king",
            "Regular Hour Rate": 0.0,
            "Overtime Hour Rate": 0.0,
            "Doubletime Hour Rate": 0.0,
            "Hourly Pension Rate": 0.0,
            "Hourly Medical": 7.24,
            "Hourly Vacation": 0.0,
            "Hourly Holiday": 0.0,
            "Apprentice Benefit Amt": 0.0,
            "Apprentice Flg (true/false)": False,
        }

        for d in range(1, 8):
            trade_row[f"Reg Day {d} Hours"] = days_dict[d]
            trade_row[f"OT Day {d} Hours"] = 0.0
            trade_row[f"DT Day {d} Hours"] = 0.0

        trades_records.append(trade_row)

    return {
        "Employees": pd.DataFrame(emp_records),
        "Trades": pd.DataFrame(trades_records),
    }

def parse_pdf_to_workbook(uploaded_file) -> dict[str, pd.DataFrame]:
    reader = PdfReader(uploaded_file)
    text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    raw_entries = []

    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\d+\.\d{2}$", line):
            hrs = float(line)
            context = lines[max(0, i - 8) : i]
            forward = lines[i + 1 : min(len(lines), i + 8)]

            date_str = "08-13-2026"
            for c in context:
                if re.match(r"\d{2}/\d{2}/\d{4}", c):
                    parsed_dt = pd.to_datetime(c, errors="coerce")
                    if pd.notna(parsed_dt):
                        date_str = parsed_dt.strftime("%m-%d-%Y")
                    break

            day_val = 1
            for c in context:
                c_lower = c.lower()[:3]
                if c_lower in DAY_MAP:
                    day_val = DAY_MAP[c_lower]
                    break

            first_name = context[0] if len(context) > 0 else "Unknown"
            last_name = context[1] if len(context) > 1 else "Worker"

            trade_str = "Unknown Trade"
            full_snippet = " ".join(context + [line] + forward).lower()
            for kpi in KNOWN_PAYROLL_ITEMS:
                if kpi.lower() in full_snippet:
                    trade_str = kpi
                    break

            raw_entries.append({
                "first": first_name,
                "last": last_name,
                "date": date_str,
                "day": day_val,
                "hours": hrs,
                "trade": trade_str,
            })
        i += 1

    unique_employees = {}
    emp_records = []
    emp_counter = 1
    trades_agg = {}

    for entry in raw_entries:
        name_key = (entry["first"], entry["last"])
        if name_key not in unique_employees:
            emp_id = f"EMP{emp_counter:02d}"
            unique_employees[name_key] = emp_id
            emp_counter += 1

            emp_records.append({
                "Employee ID": emp_id,
                "Intent ID": 1657970,
                "End of Week Date": entry["date"],
                "No Work Performed (true/false)": False,
                "First Name": entry["first"],
                "Middle Name": "",
                "Last Name": entry["last"],
                "SSN": "",
                "Ethnicity": "Prefer not to answer",
                "Gender": "?",
                "Veteran Status (Y/N/?)": "?",
                "Address 1": "",
                "Address 2": "",
                "City": "",
                "State": "WA",
                "Zip": "",
                "Gross Pay": 0.0,
                "FICA": 0.0,
                "Tax Withholding": 0.0,
            })

        emp_id = unique_employees[name_key]
        trade_key = (emp_id, entry["trade"])
        
        if trade_key not in trades_agg:
            trades_agg[trade_key] = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0, 7: 0.0}
        
        trades_agg[trade_key][entry["day"]] += entry["hours"]

    trades_records = []
    for (emp_id, trade_name), days_dict in trades_agg.items():
        trade_row = {
            "Employee ID": emp_id,
            "Trade": trade_name,
            "Job Class": "Journey Level",
            "Trade Notes": "",
            "County": "king",
            "Regular Hour Rate": 0.0,
            "Overtime Hour Rate": 0.0,
            "Doubletime Hour Rate": 0.0,
            "Hourly Pension Rate": 0.0,
            "Hourly Medical": 7.24,
            "Hourly Vacation": 0.0,
            "Hourly Holiday": 0.0,
            "Apprentice Benefit Amt": 0.0,
            "Apprentice Flg (true/false)": False,
        }

        for d in range(1, 8):
            trade_row[f"Reg Day {d} Hours"] = days_dict[d]
            trade_row[f"OT Day {d} Hours"] = 0.0
            trade_row[f"DT Day {d} Hours"] = 0.0

        trades_records.append(trade_row)

    return {
        "Employees": pd.DataFrame(emp_records),
        "Trades": pd.DataFrame(trades_records),
    }

# -------------------------------------------------------------------
# XML GENERATOR
# -------------------------------------------------------------------
def build_wapwcpr_xml(all_sheets: dict[str, pd.DataFrame]) -> bytes:
    emp_df = all_sheets.get("Employees", pd.DataFrame()).dropna(how="all")
    trades_df = all_sheets.get("Trades", pd.DataFrame()).dropna(how="all")

    emp_df.columns = [str(c).strip() for c in emp_df.columns]
    trades_df.columns = [str(c).strip() for c in trades_df.columns]

    if "Employee ID" in emp_df.columns:
        emp_df = emp_df[
            emp_df["Employee ID"].notna()
            & (emp_df["Employee ID"].astype(str).str.strip() != "")
        ]

    if "Trade" in trades_df.columns:
        trades_df = trades_df[trades_df["Trade"].notna()]

    intent_id = "0"
    end_date = "2026-08-13"
    if not emp_df.empty:
        if "Intent ID" in emp_df.columns and pd.notna(emp_df["Intent ID"].iloc[0]):
            intent_id = str(int(float(emp_df["Intent ID"].iloc[0])))
        if "End of Week Date" in emp_df.columns and pd.notna(emp_df["End of Week Date"].iloc[0]):
            raw_date = str(emp_df["End of Week Date"].iloc[0]).split(" ")[0]
            try:
                end_date = pd.to_datetime(raw_date, format="%m-%d-%Y").strftime("%Y-%m-%d")
            except ValueError:
                end_date = raw_date

    root = etree.Element("WaPWCPR")
    proj_intent = etree.SubElement(root, "projectIntent")
    etree.SubElement(proj_intent, "intentId").text = intent_id

    payroll = etree.SubElement(root, "payroll")
    payroll_week = etree.SubElement(payroll, "payrollWeek")
    etree.SubElement(payroll_week, "endOfWeekDate").text = end_date
    etree.SubElement(payroll_week, "noWorkPerformFlag").text = "false"

    employees_node = etree.SubElement(payroll_week, "employees")

    for _, emp in emp_df.iterrows():
        emp_id = str(emp.get("Employee ID", "")).strip()
        if not emp_id or emp_id.lower() == "nan":
            continue

        emp_node = etree.SubElement(employees_node, "employee")
        etree.SubElement(emp_node, "firstName").text = str(
            emp.get("First Name", "")
        ).strip()

        mid_name = emp.get("Middle Name")
        if pd.notna(mid_name) and str(mid_name).strip() and str(mid_name).lower() not in ["nan", "0"]:
            etree.SubElement(emp_node, "midName").text = str(mid_name).strip()

        etree.SubElement(emp_node, "lastName").text = str(
            emp.get("Last Name", "")
        ).strip()
        etree.SubElement(emp_node, "ssn").text = format_ssn(emp.get("SSN"))

        eth = emp.get("Ethnicity")
        if pd.notna(eth) and str(eth).strip() and str(eth).lower() not in ["nan", "0"]:
            etree.SubElement(emp_node, "ethnicity").text = str(eth).strip()

        etree.SubElement(emp_node, "gender").text = map_gender(emp.get("Gender"))
        etree.SubElement(emp_node, "veteranStatus").text = map_veteran(emp.get("Veteran Status (Y/N/?)"))
        etree.SubElement(emp_node, "address1").text = str(emp.get("Address 1", "")).strip()

        addr2 = emp.get("Address 2")
        if pd.notna(addr2) and str(addr2).strip() and str(addr2).lower() not in ["nan", "0"]:
            etree.SubElement(emp_node, "address2").text = str(addr2).strip()

        etree.SubElement(emp_node, "city").text = str(emp.get("City", "")).strip()
        raw_state = str(emp.get("State", "WA")).strip()
        etree.SubElement(emp_node, "state").text = "WA" if "wash" in raw_state.lower() else raw_state[:2].upper()
        etree.SubElement(emp_node, "zip").text = str(emp.get("Zip", "")).strip()

        gross = emp.get("Gross Pay", 0.0)
        etree.SubElement(emp_node, "grossPay").text = f"{float(gross if pd.notna(gross) else 0):.2f}"

        fica = emp.get("FICA")
        if pd.notna(fica) and str(fica).strip() and str(fica).lower() not in ["nan", "0"]:
            etree.SubElement(emp_node, "fica").text = f"{float(fica):.2f}"

        tax = emp.get("Tax Withholding")
        if pd.notna(tax) and str(tax).strip() and str(tax).lower() not in ["nan", "0"]:
            etree.SubElement(emp_node, "taxWitholding").text = f"{float(tax):.2f}"

        trade_df_emp = trades_df[trades_df["Employee ID"] == emp_id]
        if not trade_df_emp.empty:
            trade_hw = etree.SubElement(emp_node, "tradeHoursWages")
            for _, tr in trade_df_emp.iterrows():
                tr_node = etree.SubElement(trade_hw, "tradeHoursWage")
                etree.SubElement(tr_node, "trade").text = clean_trade_code(tr.get("Trade"))

                jclass = tr.get("Job Class")
                if pd.notna(jclass) and str(jclass).strip() and str(jclass).lower() not in ["nan", "0"]:
                    etree.SubElement(tr_node, "jobClass").text = str(jclass).strip()

                tnotes = tr.get("Trade Notes")
                if pd.notna(tnotes) and str(tnotes).strip() and str(tnotes).lower() not in ["nan", "0"]:
                    etree.SubElement(tr_node, "tradeNotes").text = str(tnotes).strip()

                etree.SubElement(tr_node, "county").text = clean_county(tr.get("County"))

                reg_rate = format_rate_or_empty(tr.get("Regular Hour Rate"))
                etree.SubElement(tr_node, "regularHourRateAmt").text = reg_rate if reg_rate else "0.01"
                etree.SubElement(tr_node, "overtimeHourRateAmt").text = format_rate_or_empty(tr.get("Overtime Hour Rate"))
                etree.SubElement(tr_node, "doubletimeHourRateAmt").text = format_rate_or_empty(tr.get("Doubletime Hour Rate"))
                etree.SubElement(tr_node, "hourlyPensionRateAmt").text = format_benefit_rate(tr.get("Hourly Pension Rate"))
                etree.SubElement(tr_node, "hourlyMedicalAmt").text = format_benefit_rate(tr.get("Hourly Medical"))
                etree.SubElement(tr_node, "hourlyVacationAmt").text = format_benefit_rate(tr.get("Hourly Vacation"))
                etree.SubElement(tr_node, "hourlyHolidayAmt").text = format_benefit_rate(tr.get("Hourly Holiday"))
                etree.SubElement(tr_node, "apprenticeBenefitAmt").text = format_benefit_rate(tr.get("Apprentice Benefit Amt"))

                app_flag = str(tr.get("Apprentice Flg (true/false)", "false")).strip().lower()
                etree.SubElement(tr_node, "apprenticeFlg").text = "true" if app_flag == "true" else "false"

                for day in range(1, 8):
                    etree.SubElement(tr_node, f"regularDay{day}Hours").text = format_hours(tr.get(f"Reg Day {day} Hours"))
                for day in range(1, 8):
                    etree.SubElement(tr_node, f"overtimeDay{day}Hours").text = format_hours(tr.get(f"OT Day {day} Hours"))
                for day in range(1, 8):
                    etree.SubElement(tr_node, f"doubletimeDay{day}Hours").text = format_hours(tr.get(f"DT Day {day} Hours"))

    tree = etree.ElementTree(root)
    out = io.BytesIO()
    tree.write(out, pretty_print=True, xml_declaration=True, encoding="utf-8")
    return out.getvalue()

def validate_xml_data(xml_bytes: bytes, xsd_path: str):
    with open(xsd_path, "rb") as f:
        schema_doc = etree.XML(f.read())
        schema = etree.XMLSchema(schema_doc)
    xml_doc = etree.parse(io.BytesIO(xml_bytes))
    is_valid = schema.validate(xml_doc)
    return is_valid, schema.error_log

# -------------------------------------------------------------------
# STREAMLIT UI
# -------------------------------------------------------------------
st.subheader("Upload Timesheet File")
uploaded_file = st.file_uploader("Upload Timesheet", type=["xlsx", "xls", "pdf"])

if "active_workbook" not in st.session_state:
    st.session_state.active_workbook = None

if uploaded_file:
    file_name = uploaded_file.name.lower()
    if file_name.endswith(".pdf"):
        st.session_state.active_workbook = parse_pdf_to_workbook(uploaded_file)
        st.success("PDF timesheet parsed")
    else:
        st.session_state.active_workbook = parse_excel_to_workbook(uploaded_file)
        st.success("Excel timesheet parsed")

if st.session_state.active_workbook:
    st.markdown("---")
    st.subheader("Review & Edit Extracted Data")
    st.info("You can edit cells in the tables below before generating the XML by double-clicking")

    preview_tabs = st.tabs(list(st.session_state.active_workbook.keys()))
    updated_workbook = {}

    for idx, (s_name, s_df) in enumerate(st.session_state.active_workbook.items()):
        with preview_tabs[idx]:
            # st.data_editor makes the spreadsheet fully interactive and editable
            edited_df = st.data_editor(
                s_df, 
                key=f"editor_{s_name}", 
                use_container_width=True, 
                num_rows="dynamic"
            )
            updated_workbook[s_name] = edited_df

    # Save any edits back into session state
    st.session_state.active_workbook = updated_workbook

    col1, col2 = st.columns(2)
    with col1:
        output_excel = io.BytesIO()
        with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
            for s_name, s_df in st.session_state.active_workbook.items():
                s_df.to_excel(writer, sheet_name=s_name, index=False)
        output_excel.seek(0)

        st.download_button(
            label="Download Current Spreadsheet (.xlsx)",
            data=output_excel,
            file_name="validated_payroll_spreadsheet.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col2:
        if st.button("Generate and Validate XML", type="primary"):
            try:
                xml_bytes = build_wapwcpr_xml(st.session_state.active_workbook)
                is_valid, error_log = validate_xml_data(xml_bytes, "schema.xsd")

                if is_valid:
                    st.success("XML successfully generated and passed L&I schema validation.")
                    st.download_button(
                        label="Download XML",
                        data=xml_bytes,
                        file_name="validated_payroll.xml",
                        mime="application/xml",
                    )
                else:
                    st.error("XML Validation Failed")
                    for error in error_log:
                        st.write(f"- Line {error.line}: {error.message}")
            except Exception as e:
                st.error(f"Error generating XML: {e}")
