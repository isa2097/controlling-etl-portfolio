import os
import logging
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Use logging instead of print statements for better debugging and information tracking
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 1. Load environment variables from .env file
load_dotenv()
DB_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
engine = create_engine(DB_URL)

# 2. Define the extract function to read data from a CSV file
def extract(filepath: str) -> pd.DataFrame:
    logging.info(f"load data from {filepath}...")
    return pd.read_csv(filepath)

def transform(df: pd.DataFrame) -> dict: # dict = {table_name : transformed_df}
    logging.info("Starting data cleaning and transformation...")
    
    # Remove duplicates
    initial_rows = len(df)
    df = df.drop_duplicates().copy()
    logging.info(f"{initial_rows - len(df)} duplicates removed.")

    # Split column: 'Transaction ID' into two columns
    df[['Transaction Prefix', 'Transaction No']] = df['Transaction ID'].str.extract(r'(\D+)(\d+)')
    
    # Replace missing values in column: 'Transaction Prefix'
    df['Transaction Prefix'] = df['Transaction Prefix'].ffill() 
    
    # Find missing values for column: 'Transaction No'
    was_na = df['Transaction No'].isna() 
    
    # Replace missing values in column: 'Transaction No'
    df['Transaction No'] = df['Transaction No'].astype('Int64').ffill() 
    
    # Increase the replaced value by 1 in column: 'Transaction No'
    df.loc[was_na, 'Transaction No'] += 1
    
    # Combine the two columns into column: 'Transaction ID'
    df['Transaction ID'] = df['Transaction Prefix'] + df['Transaction No'].astype(str)
    
    # Drop the two added columns
    df = df.drop(columns=['Transaction Prefix', 'Transaction No'])

     # Remove rows without Department or Category
    df = df.dropna(subset=["Department", "Category"]).copy()

    # Fill missing regions with 'Unknown'
    df["Region"] = df["Region"].fillna("Unknown")

    # Data Quality Check: Sicherstellen, dass keine leeren oder doppelten IDs entstanden sind
    assert df['Transaction ID'].isna().sum() == 0, "Error: there are still empty Transaction IDs!"
    assert df['Transaction ID'].is_unique, "Error: there are duplicate Transaction IDs after ffill!"

    # For column: 'Date', convert to datetime format
    df["Date"] = pd.to_datetime(df["Date"])

    # Star schema: build dimension tables
    dim_department = df[["Department"]].drop_duplicates().reset_index(drop=True)
    dim_department["department_id"] = dim_department.index + 1 # SQL auto increment starts with 1, not 0

    dim_category = df[["Category"]].drop_duplicates().reset_index(drop=True)
    dim_category["category_id"] = dim_category.index + 1

    dim_region = df[["Region"]].drop_duplicates().reset_index(drop=True)
    dim_region["region_id"] = dim_region.index + 1

    dim_payment = df[["Payment Method"]].drop_duplicates().reset_index(drop=True)
    dim_payment["payment_id"] = dim_payment.index + 1

    # Build fact table by merging the dimension tables with the original dataframe
    fact_transactions = (
        df.merge(dim_department, on="Department")
          .merge(dim_category, on="Category")
          .merge(dim_region, on="Region")
          .merge(dim_payment, on="Payment Method")
          [["Transaction ID", "Date", "department_id", "category_id", "region_id", "payment_id", "Budget Amount", "Actual Amount"]]
    )

    # Standardize column names for consistency
    fact_transactions.columns = ["transaction_id", "date", "department_id", "category_id", "region_id", "payment_id", "budget_amount", "actual_amount"]
    dim_payment.columns = ["payment_method", "payment_id"]
    dim_department.columns = ["department", "department_id"]
    dim_category.columns = ["category", "category_id"]
    dim_region.columns = ["region", "region_id"]

    return {
        "dim_department": dim_department,
        "dim_category": dim_category,
        "dim_region": dim_region,
        "dim_payment": dim_payment,
        "fact_transactions": fact_transactions
    }

def load(tables: dict):
    logging.info("Plug tables in the database...")
    with engine.begin() as conn:
        # Disable foreign key checks to avoid issues with table dependencies during loading
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
        for table_name, df in tables.items():
            df.to_sql(table_name, con=conn, if_exists="replace", index=False)
            logging.info(f"table '{table_name}' successfully loaded ({len(df)} rows).")

        # Primary key constraints are added after loading to ensure data integrity
        conn.execute(text("ALTER TABLE dim_department ADD PRIMARY KEY (department_id);"))
        conn.execute(text("ALTER TABLE dim_category ADD PRIMARY KEY (category_id);"))
        conn.execute(text("ALTER TABLE dim_region ADD PRIMARY KEY (region_id);"))
        conn.execute(text("ALTER TABLE dim_payment ADD PRIMARY KEY (payment_id);"))
        conn.execute(text("ALTER TABLE fact_transactions ADD PRIMARY KEY (transaction_id(20));"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

# The main function orchestrates the ETL process by calling the extract, transform, and load functions in sequence.
if __name__ == "__main__": # To ensure that the ETL process runs only when the script is executed directly, not when imported as a module.
    raw_data = extract("Budget_vs_Actual_Data.csv") 
    transformed_tables = transform(raw_data)
    load(transformed_tables)
    logging.info("etl process completed successfully.")