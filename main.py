import streamlit as st
import pandas as pd
import io
import os
import tempfile
import anthropic
import docx
from PyPDF2 import PdfReader
import json
import re
from datetime import datetime

# Set page configuration
st.set_page_config(
    page_title="Cap Table Tie-Out AI Assistant",
    page_icon="📊",
    layout="wide"
)

# Initialize session state variables
if 'documents' not in st.session_state:
    st.session_state.documents = {}
if 'cap_table' not in st.session_state:
    st.session_state.cap_table = None
if 'verification_results' not in st.session_state:
    st.session_state.verification_results = {}
if 'diligence_items' not in st.session_state:
    st.session_state.diligence_items = {}

# Extract text from document files
def extract_text(file):
    file_extension = os.path.splitext(file.name)[1].lower()
    
    if file_extension == '.pdf':
        try:
            pdf_reader = PdfReader(io.BytesIO(file.getvalue()))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            st.error(f"Error extracting text from PDF: {str(e)}")
            return ""
    
    elif file_extension == '.docx':
        try:
            doc = docx.Document(io.BytesIO(file.getvalue()))
            text = ""
            for para in doc.paragraphs:
                text += para.text + "\n"
            return text
        except Exception as e:
            st.error(f"Error extracting text from DOCX: {str(e)}")
            return ""
    
    elif file_extension == '.txt':
        try:
            return file.getvalue().decode('utf-8')
        except Exception as e:
            st.error(f"Error extracting text from TXT: {str(e)}")
            return ""
    
    elif file_extension in ['.xlsx', '.xls', '.csv']:
        # For spreadsheets, return the file itself
        return file
    
    else:
        st.warning(f"Unsupported file type: {file_extension}")
        return ""

# Categorize documents using Claude
def categorize_document(text, filename):
    if not isinstance(text, str):
        # This is likely a spreadsheet file
        if "cap" in filename.lower() or "table" in filename.lower():
            return "Cap Table"
        else:
            return "Spreadsheet"
    
    # Basic keyword matching for document categorization
    text_lower = text.lower()[:1000]
    
    if "certificate of incorporation" in text_lower:
        return "Certificate of Incorporation"
    elif "amendment" in text_lower and ("charter" in text_lower or "certificate" in text_lower):
        return "Charter Amendment"
    elif "board" in text_lower and ("consent" in text_lower or "resolution" in text_lower):
        return "Board Consent"
    elif "stockholder" in text_lower and "consent" in text_lower:
        return "Stockholder Consent"
    elif "purchase agreement" in text_lower:
        return "Stock Purchase Agreement"
    elif "option" in text_lower and "grant" in text_lower:
        return "Option Grant"
    elif "equity" in text_lower and "plan" in text_lower:
        return "Equity Incentive Plan"
    elif "warrant" in text_lower:
        return "Warrant Agreement"
    elif "convertible" in text_lower and "note" in text_lower:
        return "Convertible Note"
    elif "safe" in text_lower:
        return "SAFE Agreement"
    elif "409a" in text_lower or "valuation" in text_lower:
        return "409A Valuation"
    elif "transfer" in text_lower:
        return "Transfer Agreement"
    else:
        return "Other"

# Extract key info from documents using Claude
def extract_document_info(text, document_type, api_key):
    if document_type == "Cap Table" or not isinstance(text, str):
        return {"message": "Cap Table will be processed separately"}
    
    try:
        client = anthropic.Anthropic(api_key=api_key)
        
        # Create prompt based on document type
        prompt = f"""
        Extract key information from this {document_type} document related to cap table verification.
        Here are the first 3000 characters of the document:
        
        {text[:3000]}
        
        Extract information like:
        - Document date
        - Share quantities 
        - Share classes
        - Prices/valuations
        - Stakeholder names
        - Approval information
        - Any other relevant data for cap table verification
        
        Format your response as JSON with appropriate keys based on the document type.
        """
        
        response = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=800,
            temperature=0,
            system="You are an AI assistant that extracts structured information from legal documents related to cap tables. Always respond in valid JSON format.",
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Extract JSON from the response
        json_text = response.content[0].text
        # Clean up any markdown formatting
        json_text = re.sub(r'```json', '', json_text)
        json_text = re.sub(r'```', '', json_text)
        
        result = json.loads(json_text.strip())
        return result
    
    except Exception as e:
        st.error(f"Error extracting information: {str(e)}")
        return {"error": str(e)}

# Parse cap table file
def parse_cap_table(file, api_key):
    try:
        # Read the file based on extension
        file_extension = os.path.splitext(file.name)[1].lower()
        
        if file_extension in ['.xlsx', '.xls']:
            df = pd.read_excel(file)
        elif file_extension == '.csv':
            df = pd.read_csv(file)
        else:
            st.error("Unsupported cap table format. Please upload an Excel or CSV file.")
            return None
        
        # Use Claude to analyze the cap table structure
        client = anthropic.Anthropic(api_key=api_key)
        
        # Convert the first few rows to string for analysis
        table_preview = df.head(10).to_string()
        
        prompt = f"""
        Analyze this cap table and identify the key columns:
        
        {table_preview}
        
        Identify which columns represent:
        1. Stakeholder/shareholder names
        2. Share class (common, preferred, etc.)
        3. Number of shares
        4. Percentage ownership
        5. Issue date or grant date
        6. Price per share
        
        Respond in JSON format with column names as values.
        """
        
        response = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=500,
            temperature=0,
            system="You are an AI assistant that analyzes cap table structures. Respond in valid JSON format.",
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Extract column mapping from response
        json_text = response.content[0].text
        json_text = re.sub(r'```json', '', json_text)
        json_text = re.sub(r'```', '', json_text)
        
        column_mapping = json.loads(json_text.strip())
        
        # Create summary statistics
        total_rows = len(df)
        share_classes = []
        total_shares = 0
        
        # Get share classes if available
        if "share_class" in column_mapping and column_mapping["share_class"] in df.columns:
            share_classes = df[column_mapping["share_class"]].dropna().unique().tolist()
        
        # Get total shares if available
        if "shares" in column_mapping and column_mapping["shares"] in df.columns:
            # Convert to numeric, handling errors
            df[column_mapping["shares"]] = pd.to_numeric(df[column_mapping["shares"]], errors='coerce')
            total_shares = df[column_mapping["shares"]].sum()
        
        # Create structured cap table data
        cap_table_data = {
            "raw_data": df,
            "column_mapping": column_mapping,
            "summary": {
                "total_rows": total_rows,
                "total_shares": total_shares,
                "share_classes": share_classes
            }
        }
        
        return cap_table_data
    
    except Exception as e:
        st.error(f"Error parsing cap table: {str(e)}")
        return None

# Perform cap table tie-out verification using Claude
def verify_cap_table(cap_table, documents, api_key):
    try:
        client = anthropic.Anthropic(api_key=api_key)
        
        # Prepare document information
        doc_info = {}
        for doc_id, doc in documents.items():
            if "info" in doc and doc["info"]:
                doc_info[doc_id] = {
                    "type": doc["type"],
                    "info": doc["info"]
                }
        
        # Extract cap table summary and sample data
        cap_summary = cap_table["summary"]
        cap_sample = cap_table["raw_data"].head(10).to_string()
        column_mapping = cap_table["column_mapping"]
        
        # Create prompt for verification
        prompt = f"""
        Verify this cap table against supporting documents using the following due diligence checklist:
        
        DUE DILIGENCE CHECKLIST FOR CAP TABLE TIE-OUT:
        
        1. Authorized Shares Verification:
           - Verify authorized shares in charter vs. cap table
           - Check all share classes (common, preferred series)
        
        2. Share Issuances Verification:
           - Verify board approval for all issuances
           - Match issuances to stock purchase agreements
           - Confirm share counts, names, dates match
        
        3. Option Grants Verification:
           - Verify option grants match board approvals
           - Check exercise prices against 409A valuations
           - Verify vesting schedules are properly reflected
        
        4. Warrants Verification:
           - Verify warrants match agreements
           - Check exercise prices and expiration dates
           - Verify board approval for warrants
        
        5. Convertible Instruments Verification:
           - Verify convertible notes and SAFEs are properly reflected
           - Check conversion terms and valuation caps
           - Verify board approval for convertible instruments
        
        Cap table summary:
        {json.dumps(cap_summary, indent=2)}
        
        Column mapping:
        {json.dumps(column_mapping, indent=2)}
        
        Sample cap table data:
        {cap_sample}
        
        Supporting documents:
        {json.dumps(doc_info, indent=2)}
        
        Provide verification results for each checklist category, any discrepancies found, and recommendations.
        """
        
        response = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1500,
            temperature=0,
            system="You are an AI assistant that verifies cap tables against supporting documentation.",
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Process and structure the verification results
        verification_text = response.content[0].text
        
        # Second prompt to structure the results
        structure_prompt = f"""
        Convert the following cap table verification results into a structured JSON format:
        
        {verification_text}
        
        The JSON should have these main sections:
        1. "verification_results" - results for each category (authorized_shares, share_issuances, option_grants, warrants, convertible_instruments)
        2. "discrepancies" - list of specific discrepancies found
        3. "recommendations" - list of recommendations
        
        Each verification result should have a "verified" boolean and "notes" field.
        """
        
        structured_response = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1500,
            temperature=0,
            system="You are an AI assistant that structures cap table verification results into JSON format.",
            messages=[{"role": "user", "content": structure_prompt}]
        )
        
        # Extract JSON from the response
        json_text = structured_response.content[0].text
        json_text = re.sub(r'```json', '', json_text)
        json_text = re.sub(r'```', '', json_text)
        
        results = json.loads(json_text.strip())
        return results
    
    except Exception as e:
        st.error(f"Error verifying cap table: {str(e)}")
        return None

# Generate remediation plan
def generate_remediation(verification_results, api_key):
    try:
        client = anthropic.Anthropic(api_key=api_key)
        
        prompt = f"""
        Create a remediation plan for the following cap table verification results:
        
        {json.dumps(verification_results, indent=2)}
        
        The remediation plan should:
        1. Prioritize issues by severity
        2. Provide specific action steps for each discrepancy
        3. Include recommendations for documentation fixes
        4. Suggest timeline for implementation
        
        Be specific and practical with your recommendations.
        """
        
        response = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1500,
            temperature=0,
            system="You are an AI assistant that creates remediation plans for cap table discrepancies.",
            messages=[{"role": "user", "content": prompt}]
        )
        
        remediation_plan = response.content[0].text
        return remediation_plan
    
    except Exception as e:
        st.error(f"Error generating remediation plan: {str(e)}")
        return None

# Main UI
def main():
    st.title("Cap Table Tie-Out AI Assistant")
    st.write("Upload your cap table and supporting documents to verify accuracy")
    
    # Sidebar for API key
    with st.sidebar:
        st.header("Configuration")
        api_key = st.text_input("Anthropic API Key", type="password")
        if api_key:
            st.session_state.api_key = api_key
        
        st.divider()
        
        # Document statistics if available
        if st.session_state.documents:
            st.header("Document Statistics")
            doc_types = {}
            for doc in st.session_state.documents.values():
                doc_type = doc["type"]
                if doc_type in doc_types:
                    doc_types[doc_type] += 1
                else:
                    doc_types[doc_type] = 1
            
            for doc_type, count in doc_types.items():
                st.write(f"{doc_type}: {count}")
        
        # Clear button
        if st.button("Clear All Data"):
            for key in list(st.session_state.keys()):
                if key != "api_key":  # Keep the API key
                    del st.session_state[key]
            st.session_state.documents = {}
            st.session_state.cap_table = None
            st.session_state.verification_results = {}
            st.session_state.diligence_items = {}
            st.success("All data cleared")
    
    # Check if API key is set
    if "api_key" not in st.session_state or not st.session_state.api_key:
        st.warning("Please enter your Anthropic API Key in the sidebar to use the application")
        return
    
    # Create tabs
    tab1, tab2, tab3 = st.tabs(["Document Upload", "Verification", "Remediation"])
    
    # Tab 1: Document Upload
    with tab1:
        st.header("Upload Documents")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Cap Table")
            cap_table_file = st.file_uploader("Upload Cap Table (Excel or CSV)", type=["xlsx", "xls", "csv"])
            
            if cap_table_file is not None:
                if st.button("Process Cap Table"):
                    with st.spinner("Processing cap table..."):
                        cap_table_data = parse_cap_table(cap_table_file, st.session_state.api_key)
                        if cap_table_data:
                            st.session_state.cap_table = cap_table_data
                            st.success(f"Cap table processed: {cap_table_data['summary']['total_rows']} entries found")
            
            # Display cap table summary if available
            if st.session_state.cap_table:
                st.subheader("Cap Table Summary")
                st.write(f"Total Rows: {st.session_state.cap_table['summary']['total_rows']}")
                st.write(f"Total Shares: {st.session_state.cap_table['summary']['total_shares']}")
                
                if st.session_state.cap_table["summary"]["share_classes"]:
                    st.write("Share Classes:")
                    for share_class in st.session_state.cap_table["summary"]["share_classes"]:
                        st.write(f"- {share_class}")
        
        with col2:
            st.subheader("Supporting Documents")
            uploaded_files = st.file_uploader("Upload Supporting Documents", type=["pdf", "docx", "txt", "xlsx", "xls", "csv"], accept_multiple_files=True)
            
            if uploaded_files:
                process_button = st.button("Process Uploaded Documents")
                if process_button:
                    progress_bar = st.progress(0)
                    for i, file in enumerate(uploaded_files):
                        if file.name not in [doc.get("filename", "") for doc in st.session_state.documents.values()]:
                            with st.spinner(f"Processing {file.name}..."):
                                # Extract text
                                extracted_content = extract_text(file)
                                
                                if extracted_content is not None:
                                    # Categorize document
                                    category = categorize_document(extracted_content, file.name)
                                    
                                    # Generate unique ID
                                    doc_id = f"{category}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(st.session_state.documents)}"
                                    
                                    # Extract information if it's not a cap table
                                    info = None
                                    if category != "Cap Table" and isinstance(extracted_content, str):
                                        info = extract_document_info(extracted_content, category, st.session_state.api_key)
                                    
                                    # Store document
                                    st.session_state.documents[doc_id] = {
                                        "filename": file.name,
                                        "type": category,
                                        "content": extracted_content,
                                        "info": info
                                    }
                                    
                        # Update progress
                        progress_bar.progress((i + 1) / len(uploaded_files))
                    
                    st.success(f"Processed {len(uploaded_files)} documents")
        
        # Show document list
        if st.session_state.documents:
            st.header("Uploaded Documents")
            
            # Group by document type
            documents_by_type = {}
            for doc_id, doc in st.session_state.documents.items():
                doc_type = doc["type"]
                if doc_type not in documents_by_type:
                    documents_by_type[doc_type] = []
                documents_by_type[doc_type].append((doc_id, doc))
            
            # Display documents by type
            for doc_type, docs in documents_by_type.items():
                with st.expander(f"{doc_type} ({len(docs)})"):
                    for doc_id, doc in docs:
                        st.write(f"- {doc['filename']}")
    
    # Tab 2: Verification
    with tab2:
        st.header("Cap Table Verification")
        
        if not st.session_state.cap_table:
            st.warning("Please upload and process a cap table first")
        elif not st.session_state.documents:
            st.warning("Please upload supporting documents first")
        else:
            # Verify button
            if "verification_results" not in st.session_state or not st.session_state.verification_results:
                if st.button("Verify Cap Table"):
                    with st.spinner("Verifying cap table against supporting documents..."):
                        results = verify_cap_table(st.session_state.cap_table, st.session_state.documents, st.session_state.api_key)
                        if results:
                            st.session_state.verification_results = results
                            st.success("Verification completed")
                            st.experimental_rerun()
            
            # Display verification results
            if "verification_results" in st.session_state and st.session_state.verification_results:
                # Get verification categories
                verification_categories = st.session_state.verification_results.get("verification_results", {})
                
                # Display verification status for each category
                st.subheader("Verification Results")
                
                for category, result in verification_categories.items():
                    with st.expander(f"{category.replace('_', ' ').title()} - {'✅ Verified' if result.get('verified', False) else '❌ Issues Found'}"):
                        st.write(result.get("notes", "No notes available"))
                
                # Display discrepancies if any
                discrepancies = st.session_state.verification_results.get("discrepancies", [])
                if discrepancies:
                    st.subheader("Discrepancies Found")
                    for i, discrepancy in enumerate(discrepancies):
                        severity = discrepancy.get("severity", "medium").lower()
                        severity_color = {
                            "high": "red",
                            "medium": "orange",
                            "low": "green"
                        }.get(severity, "black")
                        
                        st.markdown(f"**{i+1}. {discrepancy.get('type', 'Issue')}** - <span style='color:{severity_color}'>{severity.upper()}</span>", unsafe_allow_html=True)
                        st.write(discrepancy.get("description", "No description available"))
                        st.write(f"*Recommendation: {discrepancy.get('recommendation', 'None provided')}*")
                        st.divider()
                
                # Display recommendations
                recommendations = st.session_state.verification_results.get("recommendations", [])
                if recommendations:
                    st.subheader("Recommendations")
                    for i, recommendation in enumerate(recommendations):
                        st.write(f"{i+1}. {recommendation}")
    
    # Tab 3: Remediation
    with tab3:
        st.header("Remediation Plan")
        
        if not st.session_state.verification_results:
            st.warning("Please verify the cap table first (in the Verification tab)")
        else:
            if "remediation_plan" not in st.session_state or not st.session_state.remediation_plan:
                if st.button("Generate Remediation Plan"):
                    with st.spinner("Generating remediation plan..."):
                        plan = generate_remediation(st.session_state.verification_results, st.session_state.api_key)
                        if plan:
                            st.session_state.remediation_plan = plan
                            st.success("Remediation plan generated")
            
            # Display remediation plan
            if "remediation_plan" in st.session_state and st.session_state.remediation_plan:
                st.markdown(st.session_state.remediation_plan)
                
                # Option to download as text
                if st.download_button(
                    label="Download Remediation Plan",
                    data=st.session_state.remediation_plan,
                    file_name="cap_table_remediation_plan.txt",
                    mime="text/plain"
                ):
                    st.success("Remediation plan downloaded successfully")

if __name__ == "__main__":
    main()
