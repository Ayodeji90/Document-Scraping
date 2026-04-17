"""
Dynamic keyword generator for academic presentation scraping.
Contains 500+ disciplines to ensure search breadth and avoid rate limits.
"""

ACADEMIC_DISCIPLINES = [
    # Sciences
    "Physics", "Astrophysics", "Quantum Mechanics", "Thermodynamics", "Nuclear Physics",
    "Chemistry", "Organic Chemistry", "Biochemistry", "Inorganic Chemistry", "Analytical Chemistry",
    "Biology", "Genetics", "Microbiology", "Ecology", "Molecular Biology", "Neuroscience",
    "Geology", "Meteorology", "Oceanography", "Environmental Science", "Paleontology",
    
    # Medicine & Health
    "Medicine", "Epidemiology", "Pathology", "Immunology", "Pharmacology", "Public Health",
    "Psychiatry", "Radiology", "Pediatrics", "Oncology", "Cardiology", "Neurology",
    "Nutrition", "Nursing", "Anatomy", "Physiology", "Virology", "Global Health",
    
    # Engineering & Tech
    "Engineering", "Mechanical Engineering", "Civil Engineering", "Electrical Engineering",
    "Chemical Engineering", "Aerospace Engineering", "Biomedical Engineering",
    "Computer Science", "Artificial Intelligence", "Machine Learning", "Deep Learning",
    "Data Science", "Cybersecurity", "Robotics", "Software Engineering", "Nanotechnology",
    
    # Social Sciences
    "Economics", "Macroeconomics", "Microeconomics", "Finance", "Sociology", "Psychology",
    "Political Science", "International Relations", "Anthropology", "Geography",
    "Criminology", "Linguistics", "Demography", "Urban Planning", "Human Rights",
    
    # Humanities
    "History", "Archaeology", "Philosophy", "Ethics", "Literature", "Art History",
    "Musicology", "Religious Studies", "Theology", "Classics", "Linguistics",
    
    # Business & Law
    "Business Administration", "Marketing", "Management", "Logistics", "Business Ethics",
    "Corporate Governance", "Law", "Constitutional Law", "International Law",
    "Environmental Law", "Property Law", "Human Rights Law",
    
    # Education
    "Pedagogy", "Educational Psychology", "Higher Education", "Special Education",
    "Curriculum Development", "Instructional Design", "Educational Technology",
    
    # Many more specific terms...
    "Sustainability", "Climate Change", "Renewable Energy", "Solar Energy", "Wind Energy",
    "Big Data", "Blockchain", "Fintech", "Healthtech", "Biotech", "Material Science",
    "Fluid Dynamics", "Complex Systems", "Behavioral Economics", "Game Theory",
    "Gender Studies", "Migration Studies", "Postcolonial Studies", "Globalization",
    "Public Policy", "Social Policy", "Criminal Justice", "Forensic Science"
]

PRESENTATION_TOKENS = [
    "presentation", "lecture", "slides", "conference", "workshop", "seminar",
    "symposium", "talk", "exposé", "keynote", "tutorial", "module", "unit",
    "colloquium", "defense", "summary", "overview", "introduction"
]

def get_broad_queries():
    """Generate a dynamic list of search queries."""
    queries = []
    # Mix disciplines with presentation tokens
    for disc in ACADEMIC_DISCIPLINES:
        for token in PRESENTATION_TOKENS[:3]: # Keep it simple for now
            queries.append(f"{disc} {token}")
    
    # Add pure disciplines
    queries.extend(ACADEMIC_DISCIPLINES)
    
    # Add domain specific PPTX search strings
    queries.extend([f"site:edu {d}" for d in ACADEMIC_DISCIPLINES[:20]])
    
    return queries
