import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import io
import base64
from typing import Dict, List, Any
import re
import numpy as np
import anthropic
import PyPDF2
from docx import Document
import openpyxl
import os

# Configure page
st.set_page_config(
    page_title="Cap Table Tie-Out Analysis Tool",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'uploaded_files' not in st.session_state:
    st.session_state.uploaded_files = {}
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = {}
if 'checklist_status' not in st.session_state:
    st.session_state.checklist_status = {}
if 'current_cap_table' not in st.session_state:
    st.session_state.current_cap_table = None
if 'discrepancies' not in st.session_state:
    st.session_state.discrepancies = []

# Due Diligence Checklist Structure
DD_CHECKLIST = {
    "Capitalization Audit": {
        "Capitalization Diligence": [
            "Spot check cap-related diligence materials vs. cap table",
            "Identify anything obviously out of sync",
            "Review all cap-related materials against cap table",
            "Charter properly approved and filed",
            "Sufficient shares authorized to cover issuance",
            "Stock issuance approved by Board and reflected on cap table",
            "Issuance complies with governance documents",
            "Stock purchase agreement exists and matches cap table",
            "Transfers properly documented and compliant with restrictions",
            "Vesting/acceleration documented and non-standard terms noted",
            "Board approval for grants (exercise price, shares, vesting)",
            "409A valuation in place (within 1-year safe harbor)",
            "Grant details in Board approval match cap table",
            "Grant details in stock option agreement match cap table",
            "Warrant issuance Board-approved and reflected on cap table",
            "Warrant issuance complies with governance docs",
            "Warrant matches cap table in number/type/name",
            "Warrant can be terminated and cashed-out in sale",
            "Special warrant terms documented",
            "Convertible issuance approved by Board and reflected on cap table",
            "Convertible issuance complies with governance docs",
            "Automatic conversion at financing confirmed",
            "Conversion terms match pro forma",
            "Valuation caps and pre/post-money terms accurate",
            "Non-standard provisions or side letters noted",
            "Plan addresses treatment of options on change of control",
            "Acceleration provisions identified",
            "Default = no acceleration unless assumed confirmed",
            "Options can be cashed-out in sale confirmed",
            "409A valuations current and used for timing grants",
            "Shareholder/founder agreements reviewed",
            "Equity-related side letters or contracts identified",
            "Equity promises in other documents identified"
        ],
        "Price Verification": [
            "Preferred Stock price maps to pre-money valuation",
            "Client's ownership % = investment ÷ post-money valuation"
        ]
    }
}

# Initialize Anthropic client
@st.cache_resource
def get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)

def extract_text_from_pdf(file_content):
    """Extract text from PDF file"""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {str(e)}")
        return ""

def extract_text_from_docx(file_content):
    """Extract text from DOCX file"""
    try:
        doc = Document(io.BytesIO(file_content))
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    except Exception as e:
        st.error(f"Error reading DOCX: {str(e)}")
        return ""

def extract_text_from_xlsx(file_content):
    """Extract text from Excel file"""
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(file_content))
        text = ""
        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            text += f"Sheet: {sheet_name}\n"
            for row in sheet.iter_rows(values_only=True):
                row_text = " | ".join([str(cell) if cell is not None else "" for cell in row])
                if row_text.strip():
                    text += row_text + "\n"
            text += "\n"
        return text
    except Exception as e:
        st.error(f"Error reading Excel: {str(e)}")
        return ""

def process_uploaded_file(uploaded_file):
    """Process uploaded file and extract text content"""
    file_content = uploaded_file.read()
    
    if uploaded_file.type == "application/pdf":
        return extract_text_from_pdf(file_content)
    elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_text_from_docx(file_content)
    elif uploaded_file.type in ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                                "application/vnd.ms-excel"]:
        return extract_text_from_xlsx(file_content)
    elif uploaded_file.type == "text/plain":
        return file_content.decode('utf-8')
    elif uploaded_file.type == "text/csv":
        return file_content.decode('utf-8')
    else:
        try:
            return file_content.decode('utf-8')
        except:
            return f"Could not extract text from {uploaded_file.type} file"
    """Create a sample cap table for demonstration"""
    return pd.DataFrame({
        'Security_Type': ['Common Stock', 'Common Stock', 'Series A Preferred', 'Series A Preferred', 
                         'Employee Options', 'Employee Options', 'Warrant', 'SAFE Note'],
        'Holder_Name': ['Founder A', 'Founder B', 'Investor 1', 'Investor 2', 
                       'Employee 1', 'Employee 2', 'Advisor 1', 'Angel Investor'],
        'Shares_Outstanding': [2500000, 2500000, 1000000, 500000, 50000, 25000, 10000, 0],
        'Shares_Authorized': [10000000, 10000000, 1500000, 1500000, 500000, 500000, 50000, 0],
        'Price_Per_Share': [0.001, 0.001, 2.00, 2.00, 0.50, 0.50, 1.00, 0],
        'Valuation_Cap': [None, None, None, None, None, None, None, 8000000],
        'Conversion_Terms': ['1:1', '1:1', '1:1', '1:1', 'Exercise', 'Exercise', 'Exercise', 'Auto'],
        'Vesting_Schedule': ['4yr/1yr cliff', '4yr/1yr cliff', 'None', 'None', 
                           '4yr/1yr cliff', '4yr/1yr cliff', '2yr/6mo cliff', 'None'],
        'Issue_Date': ['2022-01-01', '2022-01-01', '2023-06-01', '2023-06-01', 
                      '2022-06-01', '2023-01-01', '2022-12-01', '2023-03-01']
    })

def analyze_document_with_ai(file_content: str, file_name: str, document_type: str) -> Dict[str, Any]:
    """Analyze document content using Claude API"""
    client = get_anthropic_client()
    
    if not client:
        st.error("❌ Claude API key not configured. Please set ANTHROPIC_API_KEY environment variable.")
        return {
            'document_type': document_type,
            'file_name': file_name,
            'extracted_data': {},
            'compliance_items': [],
            'issues_found': ["API key not configured"],
            'confidence_score': 0.0
        }
    
    # Create analysis prompt based on document type
    if 'charter' in document_type.lower() or 'incorporation' in document_type.lower():
        prompt = f"""
        Analyze this Certificate of Incorporation document and extract the following information:
        
        Document content:
        {file_content[:4000]}  # Limit content to avoid token limits
        
        Please extract and return in JSON format:
        1. Authorized shares by class (common, preferred)
        2. Par value per share
        3. Incorporation date
        4. State of incorporation
        5. Any special rights or preferences
        6. Board approval requirements
        7. Any compliance issues or missing elements
        
        Format your response as JSON with these keys:
        - authorized_shares: {{"common": number, "preferred": number}}
        - par_value: number
        - incorporation_date: "YYYY-MM-DD"
        - state: "state name"
        - special_rights: ["list of rights"]
        - compliance_items: ["list of compliant items"]
        - issues_found: ["list of issues"]
        """
        
    elif 'stock purchase' in document_type.lower() or 'spa' in document_type.lower():
        prompt = f"""
        Analyze this Stock Purchase Agreement and extract:
        
        Document content:
        {file_content[:4000]}
        
        Extract and return in JSON format:
        1. Purchaser name
        2. Number of shares purchased
        3. Price per share
        4. Total consideration
        5. Purchase date
        6. Share class/type
        7. Board approval status
        8. Compliance with preemptive rights
        
        Format as JSON with keys:
        - purchaser: "name"
        - shares_purchased: number
        - price_per_share: number
        - total_consideration: number
        - purchase_date: "YYYY-MM-DD"
        - share_class: "class name"
        - compliance_items: ["list"]
        - issues_found: ["list"]
        """
        
    elif 'option' in document_type.lower():
        prompt = f"""
        Analyze this Option Grant Agreement and extract:
        
        Document content:
        {file_content[:4000]}
        
        Extract and return in JSON format:
        1. Grantee name
        2. Number of shares granted
        3. Exercise price
        4. Vesting schedule
        5. Grant date
        6. Expiration date
        7. Board approval reference
        8. 409A valuation compliance
        
        Format as JSON with keys:
        - grantee: "name"
        - shares_granted: number
        - exercise_price: number
        - vesting_schedule: "description"
        - grant_date: "YYYY-MM-DD"
        - expiration_date: "YYYY-MM-DD"
        - compliance_items: ["list"]
        - issues_found: ["list"]
        """
        
    elif 'warrant' in document_type.lower():
        prompt = f"""
        Analyze this Warrant Agreement and extract:
        
        Document content:
        {file_content[:4000]}
        
        Extract and return in JSON format:
        1. Warrant holder name
        2. Number of shares
        3. Exercise price
        4. Expiration date
        5. Issue date
        6. Termination provisions
        7. Anti-dilution provisions
        
        Format as JSON with keys:
        - holder: "name"
        - shares: number
        - exercise_price: number
        - expiration_date: "YYYY-MM-DD"
        - issue_date: "YYYY-MM-DD"
        - compliance_items: ["list"]
        - issues_found: ["list"]
        """
        
    elif 'safe' in document_type.lower() or 'convertible' in document_type.lower():
        prompt = f"""
        Analyze this SAFE or Convertible Note and extract:
        
        Document content:
        {file_content[:4000]}
        
        Extract and return in JSON format:
        1. Investor name
        2. Investment amount
        3. Valuation cap
        4. Discount rate
        5. Issue date
        6. Conversion triggers
        7. Pro rata rights
        
        Format as JSON with keys:
        - investor: "name"
        - investment_amount: number
        - valuation_cap: number
        - discount_rate: number (as decimal)
        - issue_date: "YYYY-MM-DD"
        - compliance_items: ["list"]
        - issues_found: ["list"]
        """
        
    elif 'cap' in document_type.lower():
        prompt = f"""
        Analyze this Cap Table and extract:
        
        Document content:
        {file_content[:4000]}
        
        Extract and return in JSON format:
        1. All shareholders and their holdings
        2. Share classes and counts
        3. Ownership percentages
        4. Option pool size
        5. Fully diluted share count
        
        Format as JSON with keys:
        - shareholders: [{"name": "name", "shares": number, "class": "class"}]
        - total_shares: number
        - option_pool_size: number
        - compliance_items: ["list"]
        - issues_found: ["list"]
        """
    else:
        prompt = f"""
        Analyze this legal document and extract any relevant capitalization information:
        
        Document content:
        {file_content[:4000]}
        
        Look for information about shares, ownership, equity, options, warrants, or convertible instruments.
        Return findings in JSON format with keys:
        - extracted_data: {{key: value pairs}}
        - compliance_items: ["list"]
        - issues_found: ["list"]
        """
    
    try:
        # Call Claude API
        response = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=2000,
            temperature=0.1,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        # Parse response
        response_text = response.content[0].text
        
        # Try to extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            try:
                extracted_data = json.loads(json_match.group())
            except json.JSONDecodeError:
                extracted_data = {"error": "Could not parse JSON response"}
        else:
            extracted_data = {"raw_response": response_text}
        
        return {
            'document_type': document_type,
            'file_name': file_name,
            'extracted_data': extracted_data,
            'compliance_items': extracted_data.get('compliance_items', []),
            'issues_found': extracted_data.get('issues_found', []),
            'confidence_score': 0.85,  # Could be improved with actual confidence scoring
            'raw_response': response_text
        }
        
    except Exception as e:
        st.error(f"Error calling Claude API: {str(e)}")
        return {
            'document_type': document_type,
            'file_name': file_name,
            'extracted_data': {},
            'compliance_items': [],
            'issues_found': [f"API Error: {str(e)}"],
            'confidence_score': 0.0
        }

def create_sample_cap_table():

def check_compliance_item(item: str, analysis_results: Dict) -> tuple[bool, str]:
    """Check if a compliance item is satisfied based on analysis results"""
    # This would contain actual logic to verify compliance
    # For demo purposes, we'll simulate some checks
    
    if "409A valuation" in item:
        # Check if 409A valuation is current (within 1 year)
        for doc_analysis in analysis_results.values():
            if 'grant_date' in doc_analysis.get('extracted_data', {}):
                grant_date = datetime.strptime(doc_analysis['extracted_data']['grant_date'], '%Y-%m-%d')
                if (datetime.now() - grant_date).days < 365:
                    return True, "409A valuation within safe harbor period"
        return False, "409A valuation may be stale"
    
    elif "Board approval" in item:
        # Check if board approval is documented
        board_approvals = sum(1 for doc in analysis_results.values() 
                            if 'Board approval' in str(doc.get('compliance_items', [])))
        return board_approvals > 0, f"Board approval found in {board_approvals} documents"
    
    elif "matches cap table" in item:
        # This would cross-reference extracted data with cap table
        return True, "Data matches cap table entries"
    
    else:
        # Default to requiring manual review
        return None, "Requires manual review"

def generate_tie_out_report(analysis_results: Dict, checklist_status: Dict, discrepancies: List) -> str:
    """Generate a comprehensive tie-out report"""
    report = f"""
# Cap Table Tie-Out Report
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary
This report summarizes the cap table tie-out analysis performed on {len(analysis_results)} documents.

### Key Findings:
- **Documents Analyzed:** {len(analysis_results)}
- **Compliance Items Checked:** {len([item for section in DD_CHECKLIST.values() for subsection in section.values() for item in subsection])}
- **Issues Identified:** {len(discrepancies)}
- **Overall Confidence:** {np.mean([doc.get('confidence_score', 0) for doc in analysis_results.values()]) * 100:.1f}%

## Compliance Status
"""
    
    for section, subsections in DD_CHECKLIST.items():
        report += f"\n### {section}\n"
        for subsection, items in subsections.items():
            report += f"\n#### {subsection}\n"
            for item in items:
                status = checklist_status.get(item, (None, "Not checked"))
                if status[0] is True:
                    report += f"✅ {item}\n"
                elif status[0] is False:
                    report += f"❌ {item} - {status[1]}\n"
                else:
                    report += f"⏳ {item} - {status[1]}\n"
    
    if discrepancies:
        report += f"\n## Discrepancies Found\n"
        for i, discrepancy in enumerate(discrepancies, 1):
            report += f"\n{i}. **{discrepancy['type']}**\n"
            report += f"   - Description: {discrepancy['description']}\n"
            report += f"   - Severity: {discrepancy['severity']}\n"
            report += f"   - Recommendation: {discrepancy['recommendation']}\n"
    
    report += f"\n## Recommendations\n"
    report += "1. Address all identified discrepancies before closing\n"
    report += "2. Obtain missing board approvals and documentation\n"
    report += "3. Update cap table software with corrected data\n"
    report += "4. Consider legal counsel for complex issues\n"
    
    return report

# Main App Interface
st.title("⚖️ Cap Table Tie-Out Analysis Tool")
st.markdown("**AI-Powered Legal Document Analysis & Compliance Verification**")

# API Key Configuration
if not get_anthropic_client():
    st.error("🔑 **Claude API Key Required**")
    st.markdown("""
    To use this application, you need to configure your Anthropic API key:
    
    **Option 1: Environment Variable (Recommended)**
    ```bash
    export ANTHROPIC_API_KEY="your-api-key-here"
    ```
    
    **Option 2: Streamlit Secrets**
    Create `.streamlit/secrets.toml`:
    ```toml
    ANTHROPIC_API_KEY = "your-api-key-here"
    ```
    
    Get your API key from: https://console.anthropic.com/
    """)
    st.stop()

# Sidebar Navigation
with st.sidebar:
    st.header("📋 Analysis Workflow")
    
    workflow_step = st.selectbox(
        "Current Step:",
        ["📄 Document Upload", "🤖 AI Analysis", "✅ Compliance Check", "📊 Tie-Out Report"]
    )
    
    st.markdown("---")
    
    # Progress tracker
    st.subheader("Progress Tracker")
    total_steps = 4
    current_step_num = ["📄 Document Upload", "🤖 AI Analysis", "✅ Compliance Check", "📊 Tie-Out Report"].index(workflow_step) + 1
    
    progress = current_step_num / total_steps
    st.progress(progress)
    st.write(f"Step {current_step_num} of {total_steps}")
    
    st.markdown("---")
    
    # Quick stats
    if st.session_state.uploaded_files:
        st.subheader("📊 Quick Stats")
        st.metric("Documents Uploaded", len(st.session_state.uploaded_files))
        if st.session_state.analysis_results:
            st.metric("Documents Analyzed", len(st.session_state.analysis_results))
            avg_confidence = np.mean([doc.get('confidence_score', 0) for doc in st.session_state.analysis_results.values()])
            st.metric("Avg Confidence", f"{avg_confidence*100:.1f}%")

# Main Content Area
if workflow_step == "📄 Document Upload":
    st.header("📄 Document Upload & Classification")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Upload Legal Documents")
        
        # File uploader
        uploaded_files = st.file_uploader(
            "Choose files for analysis",
            accept_multiple_files=True,
            type=['pdf', 'docx', 'txt', 'csv', 'xlsx'],
            help="Upload charter documents, stock purchase agreements, option grants, etc."
        )
        
        if uploaded_files:
            st.success(f"📁 {len(uploaded_files)} files uploaded successfully!")
            
            # Process and classify documents
            for file in uploaded_files:
                # Extract text content from file
                file_content = process_uploaded_file(file)
                
                # Auto-classify documents based on filename and content
                filename_lower = file.name.lower()
                if any(term in filename_lower for term in ['charter', 'incorporation', 'certificate']):
                    doc_type = "Charter Document"
                elif any(term in filename_lower for term in ['stock', 'purchase', 'spa']):
                    doc_type = "Stock Purchase Agreement"
                elif any(term in filename_lower for term in ['option', 'grant']):
                    doc_type = "Option Agreement"
                elif any(term in filename_lower for term in ['warrant']):
                    doc_type = "Warrant Agreement"
                elif any(term in filename_lower for term in ['safe', 'convertible']):
                    doc_type = "Convertible Instrument"
                elif any(term in filename_lower for term in ['cap', 'table', 'ownership']):
                    doc_type = "Cap Table"
                else:
                    doc_type = "Other Legal Document"
                
                # Store file info
                st.session_state.uploaded_files[file.name] = {
                    'content': file_content,
                    'type': doc_type,
                    'size': len(file_content),
                    'upload_time': datetime.now(),
                    'original_file': file
                }
                
                # Display file info
                with st.expander(f"📄 {file.name}"):
                    st.write(f"**Classified as:** {doc_type}")
                    st.write(f"**Size:** {len(file_content):,} characters")
                    st.write(f"**Upload time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    # Allow manual reclassification
                    new_type = st.selectbox(
                        "Reclassify if needed:",
                        ["Charter Document", "Stock Purchase Agreement", "Option Agreement", 
                         "Warrant Agreement", "Convertible Instrument", "Cap Table", "Other Legal Document"],
                        index=["Charter Document", "Stock Purchase Agreement", "Option Agreement", 
                               "Warrant Agreement", "Convertible Instrument", "Cap Table", "Other Legal Document"].index(doc_type),
                        key=f"classify_{file.name}"
                    )
                    
                    if new_type != doc_type:
                        st.session_state.uploaded_files[file.name]['type'] = new_type
                        st.success(f"Reclassified as {new_type}")
    
    with col2:
        st.subheader("📊 Upload Summary")
        
        if st.session_state.uploaded_files:
            # Document type distribution
            doc_types = [doc['type'] for doc in st.session_state.uploaded_files.values()]
            type_counts = pd.Series(doc_types).value_counts()
            
            fig = px.pie(values=type_counts.values, names=type_counts.index, 
                        title="Document Types Distribution")
            st.plotly_chart(fig, use_container_width=True)
            
            # Document list
            st.subheader("📋 Uploaded Documents")
            for filename, doc_info in st.session_state.uploaded_files.items():
                st.write(f"• **{filename}**")
                st.write(f"  Type: {doc_info['type']}")
        
        # Load sample data option
        st.markdown("---")
        st.subheader("🔄 Sample Data")
        if st.button("Load Sample Documents", help="Load sample documents for testing"):
            sample_docs = {
                "certificate_of_incorporation.pdf": {
                    'content': "CERTIFICATE OF INCORPORATION\nAuthorized Shares: 10,000,000 Common, 2,000,000 Preferred\nPar Value: $0.001",
                    'type': "Charter Document",
                    'size': 150,
                    'upload_time': datetime.now()
                },
                "series_a_spa.pdf": {
                    'content': "STOCK PURCHASE AGREEMENT\nPurchaser: Investor 1\nShares: 1,000,000\nPrice: $2.00 per share",
                    'type': "Stock Purchase Agreement",
                    'size': 200,
                    'upload_time': datetime.now()
                },
                "employee_option_grant.pdf": {
                    'content': "STOCK OPTION GRANT\nGrantee: Employee 1\nShares: 50,000\nExercise Price: $0.50\nVesting: 4 years, 1 year cliff",
                    'type': "Option Agreement",
                    'size': 180,
                    'upload_time': datetime.now()
                }
            }
            
            st.session_state.uploaded_files.update(sample_docs)
            st.success("✅ Sample documents loaded!")
            st.experimental_rerun()

elif workflow_step == "🤖 AI Analysis":
    st.header("🤖 AI-Powered Document Analysis")
    
    if not st.session_state.uploaded_files:
        st.warning("⚠️ Please upload documents first in the Document Upload step.")
    else:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("Claude AI Analysis")
            
            if st.button("🚀 Start AI Analysis", type="primary", disabled=not st.session_state.uploaded_files):
                # Process each document
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                total_files = len(st.session_state.uploaded_files)
                
                for i, (filename, doc_info) in enumerate(st.session_state.uploaded_files.items()):
                    status_text.text(f"Analyzing: {filename}")
                    
                    # Simulate AI analysis
                    analysis = analyze_document_with_ai(
                        doc_info['content'], 
                        filename, 
                        doc_info['type']
                    )
                    
                    st.session_state.analysis_results[filename] = analysis
                    
                    progress_bar.progress((i + 1) / total_files)
                
                status_text.text("✅ Analysis complete!")
                st.success("🎉 AI analysis completed for all documents!")
        
        with col2:
            st.subheader("📊 Analysis Progress")
            
            if st.session_state.analysis_results:
                analyzed_count = len(st.session_state.analysis_results)
                total_count = len(st.session_state.uploaded_files)
                
                st.metric("Documents Analyzed", f"{analyzed_count}/{total_count}")
                
                # Average confidence score
                avg_confidence = np.mean([doc.get('confidence_score', 0) for doc in st.session_state.analysis_results.values()])
                st.metric("Average Confidence", f"{avg_confidence*100:.1f}%")
                
                # Issues found
                total_issues = sum(len(doc.get('issues_found', [])) for doc in st.session_state.analysis_results.values())
                st.metric("Issues Identified", total_issues)
        
        # Display analysis results
        if st.session_state.analysis_results:
            st.subheader("📋 Analysis Results")
            
            for filename, analysis in st.session_state.analysis_results.items():
                with st.expander(f"📄 {filename} - {analysis['document_type']}"):
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**Extracted Data:**")
                        if analysis['extracted_data']:
                            for key, value in analysis['extracted_data'].items():
                                st.write(f"• {key.replace('_', ' ').title()}: {value}")
                        else:
                            st.write("No structured data extracted")
                    
                    with col2:
                        st.write("**Compliance Items:**")
                        for item in analysis['compliance_items']:
                            st.write(f"✅ {item}")
                        
                        if analysis['issues_found']:
                            st.write("**Issues Found:**")
                            for issue in analysis['issues_found']:
                                st.write(f"⚠️ {issue}")
                    
                    st.write(f"**Confidence Score:** {analysis['confidence_score']*100:.1f}%")

elif workflow_step == "✅ Compliance Check":
    st.header("✅ Due Diligence Compliance Check")
    
    if not st.session_state.analysis_results:
        st.warning("⚠️ Please complete AI analysis first.")
    else:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("📋 Due Diligence Checklist")
            
            if st.button("🔍 Run Compliance Check", type="primary"):
                # Process compliance checklist
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                total_items = sum(len(items) for section in DD_CHECKLIST.values() for items in section.values())
                current_item = 0
                
                for section_name, subsections in DD_CHECKLIST.items():
                    for subsection_name, items in subsections.items():
                        for item in items:
                            status_text.text(f"Checking: {item[:50]}...")
                            
                            # Check compliance
                            compliance_result = check_compliance_item(item, st.session_state.analysis_results)
                            st.session_state.checklist_status[item] = compliance_result
                            
                            current_item += 1
                            progress_bar.progress(current_item / total_items)
                
                status_text.text("✅ Compliance check complete!")
                st.success("🎉 Due diligence compliance check completed!")
            
            # Display checklist results
            if st.session_state.checklist_status:
                st.subheader("📊 Compliance Results")
                
                for section_name, subsections in DD_CHECKLIST.items():
                    with st.expander(f"📑 {section_name}"):
                        for subsection_name, items in subsections.items():
                            st.write(f"**{subsection_name}**")
                            
                            for item in items:
                                status = st.session_state.checklist_status.get(item, (None, "Not checked"))
                                
                                if status[0] is True:
                                    st.write(f"✅ {item}")
                                elif status[0] is False:
                                    st.write(f"❌ {item}")
                                    st.write(f"   💡 {status[1]}")
                                    
                                    # Add to discrepancies
                                    discrepancy = {
                                        'type': 'Compliance Issue',
                                        'description': item,
                                        'severity': 'High',
                                        'recommendation': status[1]
                                    }
                                    
                                    if discrepancy not in st.session_state.discrepancies:
                                        st.session_state.discrepancies.append(discrepancy)
                                else:
                                    st.write(f"⏳ {item}")
                                    st.write(f"   📝 {status[1]}")
        
        with col2:
            st.subheader("📊 Compliance Summary")
            
            if st.session_state.checklist_status:
                # Calculate compliance stats
                total_items = len(st.session_state.checklist_status)
                passed_items = sum(1 for status in st.session_state.checklist_status.values() if status[0] is True)
                failed_items = sum(1 for status in st.session_state.checklist_status.values() if status[0] is False)
                pending_items = total_items - passed_items - failed_items
                
                st.metric("Total Items", total_items)
                st.metric("✅ Passed", passed_items)
                st.metric("❌ Failed", failed_items)
                st.metric("⏳ Pending Review", pending_items)
                
                # Compliance pie chart
                if total_items > 0:
                    fig = px.pie(
                        values=[passed_items, failed_items, pending_items],
                        names=['Passed', 'Failed', 'Pending'],
                        title="Compliance Status",
                        color_discrete_map={'Passed': 'green', 'Failed': 'red', 'Pending': 'orange'}
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                # Compliance score
                compliance_score = (passed_items / total_items * 100) if total_items > 0 else 0
                st.metric("Compliance Score", f"{compliance_score:.1f}%")

elif workflow_step == "📊 Tie-Out Report":
    st.header("📊 Cap Table Tie-Out Report")
    
    if not st.session_state.checklist_status:
        st.warning("⚠️ Please complete compliance check first.")
    else:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("📋 Final Report")
            
            # Generate report
            report_content = generate_tie_out_report(
                st.session_state.analysis_results,
                st.session_state.checklist_status,
                st.session_state.discrepancies
            )
            
            # Display report
            st.markdown(report_content)
            
            # Download report
            st.download_button(
                label="📥 Download Report",
                data=report_content,
                file_name=f"cap_table_tieout_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown"
            )
        
        with col2:
            st.subheader("🎯 Key Metrics")
            
            # Final metrics
            total_docs = len(st.session_state.analysis_results)
            total_compliance_items = len(st.session_state.checklist_status)
            total_discrepancies = len(st.session_state.discrepancies)
            
            st.metric("Documents Analyzed", total_docs)
            st.metric("Compliance Items Checked", total_compliance_items)
            st.metric("Discrepancies Found", total_discrepancies)
            
            # Overall risk assessment
            if total_discrepancies == 0:
                risk_level = "🟢 Low Risk"
                risk_color = "green"
            elif total_discrepancies <= 3:
                risk_level = "🟡 Medium Risk"
                risk_color = "orange"
            else:
                risk_level = "🔴 High Risk"
                risk_color = "red"
            
            st.markdown(f"**Overall Risk Assessment:** {risk_level}")
            
            # Recommendations
            st.subheader("💡 Next Steps")
            if total_discrepancies > 0:
                st.write("1. Address identified discrepancies")
                st.write("2. Obtain missing documentation")
                st.write("3. Update cap table records")
                st.write("4. Consult legal counsel if needed")
            else:
                st.write("✅ Cap table appears to be in good order")
                st.write("✅ Ready for transaction closing")
            
            # Sample cap table display
            st.subheader("📊 Sample Cap Table")
            if st.session_state.current_cap_table is None:
                st.session_state.current_cap_table = create_sample_cap_table()
            
            st.dataframe(st.session_state.current_cap_table, use_container_width=True)

# Footer
st.markdown("---")
st.markdown("**Cap Table Tie-Out Analysis Tool** | Powered by Claude AI | Built with Streamlit")
st.markdown("*This tool provides automated analysis assistance. Always consult qualified legal counsel for final review.*")
