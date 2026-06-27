"""
Generate a couple of distinct sample PDFs for testing book upload.

These are short, original (public-domain-safe) texts with real chapter headings
so the parser detects structure. Run: python scripts/make_samples.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

SAMPLES = Path(__file__).resolve().parent.parent.parent / "samples"

styles = getSampleStyleSheet()
H = ParagraphStyle("H", parent=styles["Heading1"], fontSize=20, leading=24, spaceAfter=18)
B = ParagraphStyle("B", parent=styles["BodyText"], fontSize=11, leading=16, alignment=4)


def make(path, title, author, chapters):
    story = []
    for i, (ct, paras) in enumerate(chapters):
        if i > 0:
            story.append(PageBreak())
        story.append(Paragraph(ct, H))
        story.append(Spacer(1, 6))
        for p in paras:
            story.append(Paragraph(p, B))
    SimpleDocTemplate(
        str(path), pagesize=letter, title=title, author=author,
        leftMargin=inch, rightMargin=inch, topMargin=inch, bottomMargin=inch,
    ).build(story)
    print("wrote", path)


def main():
    SAMPLES.mkdir(exist_ok=True)
    make(SAMPLES / "field-guide-to-birds.pdf", "A Field Guide to Garden Birds", "M. Wren", [
        ("I. THE ROBIN", [
            "The European robin is among the most recognisable garden birds, distinguished by its orange-red breast and upright posture. Unlike many songbirds, the robin sings throughout the year, defending its territory even in the depths of winter. Both males and females hold territories outside the breeding season, a rare trait among British birds.",
            "Robins are fiercely territorial and will attack rivals, sometimes to the death. They are attracted to gardeners because freshly turned soil exposes the worms and grubs that form the bulk of their diet. A robin will often follow a digging spade within a few feet, waiting for the next spadeful of earth.",
        ]),
        ("II. THE BLACKBIRD", [
            "The blackbird is a member of the thrush family. The male is glossy black with a bright yellow-orange bill and a narrow yellow eye-ring; the female is dark brown, often with a spotted breast. Its mellow, fluted song, delivered from a high perch at dawn and dusk, is one of the most admired of all British bird songs.",
            "Blackbirds feed on earthworms, insects, and in autumn, berries and windfall fruit. They are ground feeders, hopping across lawns and turning over leaf litter with sideways flicks of the bill. In hard weather they will come readily to apples left out on the ground.",
        ]),
        ("III. THE BLUE TIT", [
            "The blue tit is a small, acrobatic bird with a blue cap, white cheeks, and a yellow underside. It is a frequent visitor to garden feeders, where its agility lets it hang upside down from peanut holders that larger birds cannot use.",
            "In spring the blue tit nests in holes, readily taking to nest boxes. A single brood may contain eight to twelve eggs, timed so the peak demand for food coincides with the abundance of caterpillars on oak trees. A pair may bring a thousand caterpillars a day to their young.",
        ]),
        ("IV. THE GOLDFINCH", [
            "The goldfinch is unmistakable, with its red face, black-and-white head, and broad yellow wing bars that flash in flight. It feeds chiefly on the seeds of thistles and teasels, and its fine, pointed bill extracts seeds from prickly heads other birds cannot reach.",
            "Goldfinches are sociable and often feed in twittering flocks known as charms. In recent decades they have become common garden visitors, drawn especially to nyjer seed. Their tinkling, liquid song is delivered both perched and in flight.",
        ]),
    ])


if __name__ == "__main__":
    main()
