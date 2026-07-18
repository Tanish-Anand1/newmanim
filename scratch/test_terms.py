import sys
sys.path.insert(0, 'C:\\PROJECTS\\newmanim')
import unicodedata
from app.pipeline import extract_topic_key_terms

topic = (
    "Visually explain how a Fourier Series approximates a square wave by adding odd harmonics. "
    "Show the target function as a sharp, alternating square wave. Then, step-by-step, overlay "
    "the fundamental frequency sine wave, followed by the third harmonic, and finally the fifth harmonic. "
    "With each new harmonic added, show the mathematical formula update in the text safe-zone to include "
    "the next term in the summation sequence. Ensure the transition between the individual sine waves "
    "and their combined sum is perfectly fluid, with a consistent 1.25-second breathing window between "
    "each new term insertion so the viewer can follow the complexity."
)

terms = extract_topic_key_terms(topic)
print("Extracted terms:")
for t in terms:
    print(f"- {t}")
