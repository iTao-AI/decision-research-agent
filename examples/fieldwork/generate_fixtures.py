"""Build the three fictional one-page Fieldwork PDFs."""

import argparse
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent
TITLE = "试点安排确认函"
FILENAME = "pilot-arrangement-letter.pdf"
TEXT_BY_CASE = {
    "A": (
        "关于周三客户演示",
        "允许使用脱敏导出样本进行周三客户演示。",
        "该授权限于现场服务助手试点的周三客户演示。",
        "关于实时数据",
        "实时告警接口仍未获批，须由客户 IT 单独确认读取范围与条件。",
    ),
    "B": (
        "关于周三客户演示",
        "脱敏导出样本仅限团队内部排练。",
        "向客户展示脱敏导出样本须另行取得客户 IT 书面授权。",
        "关于实时数据",
        "实时告警接口仍未获批。",
    ),
    "C": (
        "关于周三客户演示",
        "已收到周三演示数据使用申请。",
        "本函仅确认收件，未批准样本使用或实时告警接口读取。",
        "后续确认",
        "请向客户 IT 确认是否允许使用脱敏样本、适用对象与数据范围。",
    ),
}


def make_letter(path, statements):
    pine = (0.10, 0.29, 0.21)
    ink = (0.14, 0.17, 0.15)
    muted = (0.32, 0.36, 0.33)

    with pymupdf.open() as letter:
        page = letter.new_page(width=595, height=842)
        page.draw_line((57, 129), (538, 129), color=pine)

        def put(text, y, size=13, color=ink):
            # Built-in Simplified Chinese PDF font, with a selectable text layer.
            width = pymupdf.get_text_length(text, fontname="china-s", fontsize=size)
            if width > 481:
                raise ValueError(f"line exceeds page width: {text}")
            page.insert_text((57, y), text, fontsize=size, fontname="china-s", color=color)

        put("北辰装备 · 现场服务助手", 65, 12, muted)
        put(TITLE, 109, 27, pine)
        put("致现场服务助手试点团队：", 165)
        put(statements[0], 214, 15, pine)
        put(statements[1], 250)
        put(statements[2], 278)
        put(statements[3], 332, 15, pine)
        put(statements[4], 368)
        put("现场调查安排", 422, 15, pine)
        put("安排值班主管访谈、核对设备版本与操作卡，不依赖实时告警接口。", 458)
        put("北辰装备客户 IT 联络组", 536)
        page.draw_line((57, 741), (538, 741), color=(0.81, 0.83, 0.78))
        put("虚构项目材料 · 仅供试点演示验证", 772, 11, muted)
        letter.set_metadata({"title": TITLE, "author": "Fieldwork examples"})
        letter.save(path, deflate=True, no_new_id=True)

    with pymupdf.open(path) as letter:
        if len(letter) != 1:
            raise ValueError("the letter must have one page")
        text = letter[0].get_text().strip()
        for statement in statements:
            if statement not in text:
                raise ValueError(f"missing selectable text: {statement}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    args = parser.parse_args()
    for case, statements in TEXT_BY_CASE.items():
        path = args.output_dir / case / FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        make_letter(path, statements)


if __name__ == "__main__":
    main()
