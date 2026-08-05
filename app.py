import io
from lxml import etree
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="WA State Certified Payroll Tool", page_icon="🏗️"
)

st.title("WA State Certified Payroll (WaPWCPR) XML Generator")


# -------------------------------------------------------------------
# HELPER FUNCTIONS & FORMATTERS
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
    """Returns formatted 2-decimal string if > 0, else empty string per XSD rules."""
    try:
        if pd.isna(val):
            return ""
        num = float(val)
        if num > 0:
            return f"{num:.2f}"
        return ""
    except (ValueError, TypeError):
        return ""


def format_hours(val) -> str:
    """Returns formatted 1-decimal string for daily hours (e.g. '0.0', '8.0')."""
    try:
        if pd.isna(val):
            return "0.0"
        num = float(val)
        return f"{num:.1f}"
    except (ValueError, TypeError):
        return "0.0"


def clean_trade_code(val) -> str:
    """Ensures trade code matches WA state 3-4 letter code pattern (e.g., RESE, RESR, ROOF)."""
    s = str(val).strip().upper()
    if s.isalpha() and 3 <= len(s) <= 4:
        return s
    return "RESE"


def clean_county(val) -> str:
    """Ensures county is lowercase letters (e.g., skagit)."""
    s = str(val).strip().lower()
    if s.isalpha():
        return s
    return "skagit"


# -------------------------------------------------------------------
# MAIN XML GENERATOR
# -------------------------------------------------------------------
def build_wapwcpr_xml(all_sheets: dict[str, pd.DataFrame]) -> bytes:
    """Combines sheets from Excel ('Employees', 'Trades') into WA State L&I WaPWCPR XML structure."""
    emp_df = all_sheets.get("Employees", pd.DataFrame()).dropna(how="all")
    trades_df = all_sheets.get("Trades", pd.DataFrame()).dropna(how="all")

    # Clean whitespace from column names
    emp_df.columns = [str(c).strip() for c in emp_df.columns]
    trades_df.columns = [str(c).strip() for c in trades_df.columns]

    # Filter out empty/invalid employee rows
    if "Employee ID" in emp_df.columns:
        emp_df = emp_df[
            emp_df["Employee ID"].notna()
            & (emp_df["Employee ID"].astype(str).str.strip() != "")
        ]

    # Filter out bottom summary/math rows from Trades sheet
    if "Trade" in trades_df.columns:
        trades_df = trades_df[
            trades_df["Trade"].astype(str).str.strip().str.isalpha()
        ]

    # Retrieve header metadata
    intent_id = "0"
    end_date = "2026-01-01"
    if not emp_df.empty:
        if "Intent ID" in emp_df.columns and pd.notna(
            emp_df["Intent ID"].iloc[0]
        ):
            intent_id = str(int(float(emp_df["Intent ID"].iloc[0])))
        if "End of Week Date" in emp_df.columns and pd.notna(
            emp_df["End of Week Date"].iloc[0]
        ):
            end_date = str(emp_df["End of Week Date"].iloc[0]).split(" ")[0]

    # Root XML node
    root = etree.Element("WaPWCPR")

    # 1. <projectIntent>
    proj_intent = etree.SubElement(root, "projectIntent")
    etree.SubElement(proj_intent, "intentId").text = intent_id

    # 2. <payroll> -> <payrollWeek>
    payroll = etree.SubElement(root, "payroll")
    payroll_week = etree.SubElement(payroll, "payrollWeek")

    etree.SubElement(payroll_week, "endOfWeekDate").text = end_date
    etree.SubElement(payroll_week, "noWorkPerformFlag").text = "false"

    # <employees>
    employees_node = etree.SubElement(payroll_week, "employees")

    for _, emp in emp_df.iterrows():
        emp_id = str(emp.get("Employee ID", "")).strip()
        if not emp_id or emp_id.lower() == "nan":
            continue

        emp_node = etree.SubElement(employees_node, "employee")

        # Names & SSN
        etree.SubElement(emp_node, "firstName").text = str(
            emp.get("First Name", "")
        ).strip()

        mid_name = emp.get("Middle Name")
        if (
            pd.notna(mid_name)
            and str(mid_name).strip()
            and str(mid_name).lower() not in ["nan", "0"]
        ):
            etree.SubElement(emp_node, "midName").text = str(mid_name).strip()

        etree.SubElement(emp_node, "lastName").text = str(
            emp.get("Last Name", "")
        ).strip()
        etree.SubElement(emp_node, "ssn").text = format_ssn(emp.get("SSN"))

        # Demographics
        eth = emp.get("Ethnicity")
        if pd.notna(eth) and str(eth).strip() and str(eth).lower() != "nan":
            etree.SubElement(emp_node, "ethnicity").text = str(eth).strip()

        etree.SubElement(emp_node, "gender").text = map_gender(
            emp.get("Gender")
        )
        etree.SubElement(emp_node, "veteranStatus").text = map_veteran(
            emp.get("Veteran Status (Y/N/?)")
        )

        # Address & State
        etree.SubElement(emp_node, "address1").text = str(
            emp.get("Address 1", "")
        ).strip()

        addr2 = emp.get("Address 2")
        if (
            pd.notna(addr2)
            and str(addr2).strip()
            and str(addr2).lower() not in ["nan", "0"]
        ):
            etree.SubElement(emp_node, "address2").text = str(addr2).strip()

        etree.SubElement(emp_node, "city").text = str(
            emp.get("City", "")
        ).strip()

        raw_state = str(emp.get("State", "WA")).strip()
        state_code = (
            "WA" if "wash" in raw_state.lower() else raw_state[:2].upper()
        )
        etree.SubElement(emp_node, "state").text = state_code

        etree.SubElement(emp_node, "zip").text = str(
            emp.get("Zip", "")
        ).strip()

        # Financials
        gross = emp.get("Gross Pay", 0.0)
        etree.SubElement(emp_node, "grossPay").text = (
            f"{float(gross if pd.notna(gross) else 0):.2f}"
        )

        fica = emp.get("FICA")
        if (
            pd.notna(fica)
            and str(fica).strip()
            and str(fica).lower() not in ["nan", "0"]
        ):
            etree.SubElement(emp_node, "fica").text = f"{float(fica):.2f}"

        tax = emp.get("Tax Withholding")
        if (
            pd.notna(tax)
            and str(tax).strip()
            and str(tax).lower() not in ["nan", "0"]
        ):
            etree.SubElement(emp_node, "taxWitholding").text = (
                f"{float(tax):.2f}"
            )

        # 3. <tradeHoursWages>
        trade_df_emp = trades_df[trades_df["Employee ID"] == emp_id]
        if not trade_df_emp.empty:
            trade_hw = etree.SubElement(emp_node, "tradeHoursWages")
            for _, tr in trade_df_emp.iterrows():
                tr_node = etree.SubElement(trade_hw, "tradeHoursWage")

                # 1. trade (Required)
                etree.SubElement(tr_node, "trade").text = clean_trade_code(
                    tr.get("Trade")
                )

                # 2. jobClass (Optional)
                jclass = tr.get("Job Class")
                if (
                    pd.notna(jclass)
                    and str(jclass).strip()
                    and str(jclass).lower() not in ["nan", "0"]
                ):
                    etree.SubElement(tr_node, "jobClass").text = str(
                        jclass
                    ).strip()

                # 3. tradeNotes (Optional)
                tnotes = tr.get("Trade Notes")
                if (
                    pd.notna(tnotes)
                    and str(tnotes).strip()
                    and str(tnotes).lower() not in ["nan", "0"]
                ):
                    etree.SubElement(tr_node, "tradeNotes").text = str(
                        tnotes
                    ).strip()

                # 4. county (Required)
                etree.SubElement(tr_node, "county").text = clean_county(
                    tr.get("County")
                )

                # 5. regularHourRateAmt
                reg_rate = format_rate_or_empty(tr.get("Regular Hour Rate"))
                etree.SubElement(tr_node, "regularHourRateAmt").text = (
                    reg_rate if reg_rate else "0.01"
                )

                # 6. overtimeHourRateAmt
                etree.SubElement(
                    tr_node, "overtimeHourRateAmt"
                ).text = format_rate_or_empty(tr.get("Overtime Hour Rate"))

                # 7. doubletimeHourRateAmt
                etree.SubElement(
                    tr_node, "doubletimeHourRateAmt"
                ).text = format_rate_or_empty(tr.get("Doubletime Hour Rate"))

                # 8. hourlyPensionRateAmt
                etree.SubElement(
                    tr_node, "hourlyPensionRateAmt"
                ).text = format_rate_or_empty(tr.get("Hourly Pension Rate"))

                # 9. hourlyMedicalAmt
                etree.SubElement(
                    tr_node, "hourlyMedicalAmt"
                ).text = format_rate_or_empty(tr.get("Hourly Medical"))

                # 10. hourlyVacationAmt
                etree.SubElement(
                    tr_node, "hourlyVacationAmt"
                ).text = format_rate_or_empty(tr.get("Hourly Vacation"))

                # 11. hourlyHolidayAmt
                etree.SubElement(
                    tr_node, "hourlyHolidayAmt"
                ).text = format_rate_or_empty(tr.get("Hourly Holiday"))

                # 12. apprenticeBenefitAmt
                etree.SubElement(
                    tr_node, "apprenticeBenefitAmt"
                ).text = format_rate_or_empty(tr.get("Apprentice Benefit Amt"))

                # 13. apprenticeFlg
                app_flag = (
                    str(tr.get("Apprentice Flg (true/false)", "false"))
                    .strip()
                    .lower()
                )
                etree.SubElement(tr_node, "apprenticeFlg").text = (
                    "true" if app_flag == "true" else "false"
                )

                # 14. Daily Hours (placed directly under <tradeHoursWage>)
                # Regular Day 1-7 Hours
                for day in range(1, 8):
                    etree.SubElement(
                        tr_node, f"regularDay{day}Hours"
                    ).text = format_hours(tr.get(f"Reg Day {day} Hours"))

                # Overtime Day 1-7 Hours
                for day in range(1, 8):
                    etree.SubElement(
                        tr_node, f"overtimeDay{day}Hours"
                    ).text = format_hours(tr.get(f"OT Day {day} Hours"))

                # Doubletime Day 1-7 Hours
                for day in range(1, 8):
                    etree.SubElement(
                        tr_node, f"doubletimeDay{day}Hours"
                    ).text = format_hours(tr.get(f"DT Day {day} Hours"))

    tree = etree.ElementTree(root)
    out = io.BytesIO()
    tree.write(out, pretty_print=True, xml_declaration=True, encoding="utf-8")
    return out.getvalue()


def validate_xml_data(xml_bytes: bytes, xsd_path: str):
    """Validates generated XML against Washington State schema.xsd."""
    with open(xsd_path, "rb") as f:
        schema_doc = etree.XML(f.read())
        schema = etree.XMLSchema(schema_doc)

    xml_doc = etree.parse(io.BytesIO(xml_bytes))
    is_valid = schema.validate(xml_doc)
    return is_valid, schema.error_log


# -------------------------------------------------------------------
# STREAMLIT UI
# -------------------------------------------------------------------

st.subheader("1. Upload Certified Payroll Workbook")
uploaded_file = st.file_uploader("Upload Spreadsheet File (.xlsx)", type=["xlsx"])

if uploaded_file:
    all_sheets = pd.read_excel(uploaded_file, sheet_name=None)
    st.write(f"`Detected {len(all_sheets)} Tabs in Workbook`")

    st_tabs = st.tabs(list(all_sheets.keys()))
    for idx, (sheet_name, sheet_df) in enumerate(all_sheets.items()):
        with st_tabs[idx]:
            st.dataframe(sheet_df)

    st.markdown("---")
    st.subheader("2. Convert & Validate XML for WA State (WaPWCPR)")

    if st.button("Generate & Validate L&I XML"):
    with st.spinner("Generating and validating XML..."):
        xml_bytes = build_wapwcpr_xml(all_sheets)

        is_valid, error_log = validate_xml_data(xml_bytes, "schema.xsd")

        if is_valid:
            st.success(
                "XML generated and validated"
            )
            st.download_button(
                label="Download XML",
                data=xml_bytes,
                file_name="validated_payroll.xml",
                mime="application/xml",
            )
        else:
            st.error("XML Validation Failed!")
            for error in error_log:
                st.write(f"- **Line {error.line}:** {error.message}")
