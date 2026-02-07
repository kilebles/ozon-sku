import gspread
from google.oauth2.service_account import Credentials

from src.core.settings import settings


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_gspread_client() -> gspread.Client:
    credentials = Credentials.from_service_account_file(
        settings.google_credentials_path,
        scopes=SCOPES,
    )
    return gspread.authorize(credentials)


def get_spreadsheet() -> gspread.Spreadsheet:
    client = get_gspread_client()
    return client.open_by_key(settings.google_spreadsheet_id)


def get_worksheet() -> gspread.Worksheet:
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(settings.google_sheet_name)


def get_sku_with_queries() -> list[dict]:
    """
    Get SKUs with their search queries from the sheet.

    Structure:
    - Row with article in A: SKU row (C contains product name, skip it)
    - Rows after without article in A: search queries for that SKU

    Returns:
        [{'sku': str, 'queries': [{'query': str, 'row': int}, ...], 'row': int}, ...]
    """
    worksheet = get_worksheet()
    col_a = worksheet.col_values(1)  # Column A - articles/SKUs
    col_c = worksheet.col_values(3)  # Column C - names/queries

    result = []
    current_sku = None
    query_row = None

    for i in range(len(col_c)):
        article = col_a[i] if i < len(col_a) else ""
        value_c = col_c[i] if i < len(col_c) else ""

        # Skip header row
        if i == 0:
            continue

        if article:
            # New SKU row
            if current_sku is not None:
                result.append(current_sku)
            current_sku = {"sku": article, "queries": [], "row": i + 1}
        elif value_c and current_sku is not None:
            # Query row for current SKU - store row number for each query
            current_sku["queries"].append({"query": value_c, "row": i + 1})

    # Don't forget last SKU
    if current_sku is not None:
        result.append(current_sku)

    return result


def insert_results_column(header: str) -> None:
    """Insert a new column D with the given header."""
    worksheet = get_worksheet()
    # Insert column at position D (index 4)
    worksheet.insert_cols([[]], col=4)
    # Set header in D1
    worksheet.update_cell(1, 4, header)


def write_result(row: int, value: str) -> None:
    """Write result to column D at specified row."""
    worksheet = get_worksheet()
    worksheet.update_cell(row, 4, value)
