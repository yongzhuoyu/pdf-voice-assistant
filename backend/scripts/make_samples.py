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
    # A 12-chapter book that meets the assignment's "at least 10 chapters"
    # requirement while staying short enough to index in well under a minute.
    # Each chapter is self-contained with concrete, distinct facts, so Q&A is
    # clean and per-chapter isolation is easy to demonstrate.
    make(SAMPLES / "world-lighthouses.pdf", "A Field Guide to the World's Lighthouses", "E. Marsh", [
        ("I. THE PHAROS OF ALEXANDRIA", [
            "The Pharos of Alexandria, built on the island of Pharos around 280 BC, was one of the Seven Wonders of the Ancient World. Standing over one hundred metres tall, it guided ships into the busy harbour of Alexandria for nearly a thousand years. A great fire was kept burning at its summit, and a polished bronze mirror was said to reflect the flame far out to sea by night.",
            "The Pharos was toppled by a series of earthquakes between the years 956 and 1323. Its stones were later used to build a fort on the same site. The word for lighthouse in several languages, including the French 'phare', derives from its name.",
        ]),
        ("II. THE TOWER OF HERCULES", [
            "The Tower of Hercules stands at the entrance to the harbour of A Coruña in north-western Spain. Built by the Romans in the second century, it is the oldest lighthouse still in use today. Its original Roman core remains within the outer shell added during an eighteenth-century restoration.",
            "According to legend, the hero Hercules built the tower over the buried head of a defeated giant. The structure rises fifty-five metres and was declared a World Heritage Site in 2009.",
        ]),
        ("III. THE EDDYSTONE LIGHTHOUSE", [
            "The Eddystone rocks lie south of Plymouth in England, treacherous and submerged at high tide. The first lighthouse built upon them, in 1698, was an ornate wooden structure that was swept away in a great storm in 1703, taking its builder with it.",
            "The fourth and present Eddystone lighthouse, completed in 1882, was built of interlocking granite blocks, a technique that made it strong enough to withstand the heaviest seas. Its design became the model for rock lighthouses around the world.",
        ]),
        ("IV. THE BELL ROCK LIGHTHOUSE", [
            "The Bell Rock lighthouse stands on a reef off the east coast of Scotland that is covered by the sea for most of each day. Completed in 1811 by the engineer Robert Stevenson, it is the oldest surviving sea-washed lighthouse in the world.",
            "The reef takes its name from a warning bell said to have been placed there by a medieval abbot. Working only at low tide, the builders could labour for just a few hours a day, yet the tower has stood for more than two centuries with scarcely a repair to its stonework.",
        ]),
        ("V. THE LIGHTHOUSE AT CORDOUAN", [
            "Cordouan lighthouse rises from a sandbank at the mouth of the Gironde estuary on the French Atlantic coast. Begun in the sixteenth century, it is the oldest lighthouse in France still standing, and is often called the 'King of Lighthouses' for its grandeur.",
            "Unlike the plain towers of later eras, Cordouan contains a royal apartment and a chapel within its walls, decorated with marble and carved stone. It was the first lighthouse in the world to use a revolving Fresnel lens, installed in 1823.",
        ]),
        ("VI. THE CAPE HATTERAS LIGHT", [
            "The Cape Hatteras lighthouse on the coast of North Carolina marks the Diamond Shoals, a shifting bank of sand so dangerous to shipping that the waters offshore are known as the Graveyard of the Atlantic. At sixty-four metres it is the tallest brick lighthouse in the United States.",
            "In 1999, threatened by an eroding shoreline, the entire tower was lifted onto rails and moved nearly nine hundred metres inland over the course of three weeks. The remarkable feat preserved the historic light from the encroaching sea.",
        ]),
        ("VII. THE TILLAMOOK ROCK LIGHT", [
            "Tillamook Rock light stands on a basalt islet off the coast of Oregon, exposed to the full force of the Pacific. Storms have hurled rocks and even fish over its lantern, more than thirty metres above the water. Keepers nicknamed it 'Terrible Tilly'.",
            "The light was deactivated in 1957 after decades of punishing weather made it too costly to maintain. In later years the island was sold privately and, for a time, served as a columbarium for funeral urns.",
        ]),
        ("VIII. THE LÍNDESNES LIGHT", [
            "Lindesnes lighthouse stands at the southernmost tip of mainland Norway, where the North Sea meets the Skagerrak strait. A light has burned here since 1656, making it the oldest lighthouse station in Norway.",
            "The original light was a simple open coal fire sheltered behind glass. Sailors complained it was often indistinguishable from ordinary bonfires on the shore, and it was extinguished for a time before a proper tower was eventually built.",
        ]),
        ("IX. THE LA JUMENT LIGHT", [
            "La Jument lighthouse rises from a reef off the island of Ushant, at the western edge of Brittany, in some of the most violent seas in Europe. It was built between 1904 and 1911 with money left by a benefactor who had survived a shipwreck nearby.",
            "The lighthouse became famous through a 1989 photograph in which a keeper stands in the doorway as an enormous wave engulfs the tower behind him. He had come out believing the sound he heard was a rescue helicopter, and stepped back inside just in time.",
        ]),
        ("X. THE MACQUARIE LIGHTHOUSE", [
            "The Macquarie lighthouse, overlooking the entrance to Sydney Harbour in Australia, was the first lighthouse built on the Australian continent. The original tower, completed in 1818, was designed by the convict architect Francis Greenway, who was granted his freedom in reward.",
            "When the original sandstone tower began to crumble, an almost identical replacement was built alongside it in 1883, and the old tower was demolished only after the new one was lit. The two stood side by side for a time, nearly mirror images.",
        ]),
        ("XI. THE KÕPU LIGHTHOUSE", [
            "The Kõpu lighthouse stands on the island of Hiiumaa in Estonia and is one of the oldest continuously operating lighthouses in the world, in use since 1531. It was built not on the coast but on the island's highest hill, well inland.",
            "Because it predates the techniques of later tower-builders, Kõpu has no internal staircase in its original core; it was raised as a solid masonry pillar, with stairs added only centuries later. Its great age and unusual square form make it unmistakable.",
        ]),
        ("XII. THE STATUE OF LIBERTY AS A LIGHTHOUSE", [
            "From 1886 to 1902, the Statue of Liberty in New York Harbour was officially designated a lighthouse, the first in the United States to be lit by electricity. Its torch held a beam intended to guide ships into the harbour.",
            "In practice the light was too weak to be of much use to mariners, and the statue was removed from the lighthouse service after sixteen years. It remained a beloved landmark, but its brief career as a working lighthouse is now largely forgotten.",
        ]),
    ])


if __name__ == "__main__":
    main()
