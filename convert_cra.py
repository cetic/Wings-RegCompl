from docling.document_converter import DocumentConverter

# source = "./docs/cra.pdf"  # document per local path or URL
source = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202402847"
converter = DocumentConverter()
result = converter.convert(source)

# Export to Markdown
markdown_output = result.document.export_to_markdown()

with open("outputs/CRA_requirements_html.md", "w") as f:
    f.write(markdown_output)
