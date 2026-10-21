"""Bounded XLSX exports. User text is always an inline string, never a formula."""

import io
import re
import uuid
import zipfile
from datetime import date
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.identity.errors import fail
from app.modules.identity.models import User
from app.modules.inventory.catalog_service import item_query
from app.modules.inventory.models import (
    InventoryCategory,
    InventoryDocument,
    InventoryDocumentItem,
    InventoryItem,
    InventoryMovement,
    Manufacturer,
)

MAX_EXPORT_ROWS = 10_000
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ILLEGAL_XML = re.compile(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]")
KINDS = {"receipt": "Поступление", "issue": "Выдача", "reversal": "Отмена"}


def column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def workbook(title: str, headers: list[str], rows: list[list]) -> bytes:
    if len(rows) > MAX_EXPORT_ROWS:
        fail(422, "export_too_large", "В выгрузке более 10 000 строк. Уточните фильтры или период.")
    sheet = [
        f'<worksheet xmlns="{NS}"><sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        "</sheetView></sheetViews><cols>"
    ]
    for index in range(1, len(headers) + 1):
        sheet.append(f'<col min="{index}" max="{index}" width="24" customWidth="1"/>')
    sheet.append("</cols><sheetData>")
    for row_index, values in enumerate([headers, *rows], 1):
        sheet.append(f'<row r="{row_index}">')
        for index, value in enumerate(values, 1):
            cell = f"{column(index)}{row_index}"
            style = ' s="1"' if row_index == 1 else ""
            # Excel stores only 15 significant decimal digits. Large exact integers
            # are exported as text to avoid silently rounding a legal stock balance.
            if isinstance(value, int) and abs(value) <= 999_999_999_999_999:
                sheet.append(f'<c r="{cell}"{style} t="n"><v>{value}</v></c>')
            else:
                text = escape(ILLEGAL_XML.sub("", str(value) if value is not None else ""))
                sheet.append(
                    f'<c r="{cell}"{style} t="inlineStr"><is>'
                    f'<t xml:space="preserve">{text}</t></is></c>'
                )
        sheet.append("</row>")
    sheet.append(
        f'</sheetData><autoFilter ref="A1:{column(len(headers))}{len(rows) + 1}"/></worksheet>'
    )
    package = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>",
        "_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{REL}/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<workbook xmlns="{NS}" xmlns:r="{REL}"><sheets>'
        f'<sheet name="{title}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/>'
        f'<Relationship Id="rId2" Type="{REL}/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml": f'<styleSheet xmlns="{NS}">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF2E6974"/>'
        '<bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="2"><xf fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/>'
        "</cellStyles></styleSheet>",
        "xl/worksheets/sheet1.xml": "".join(sheet),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in package.items():
            archive.writestr(
                name, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + content
            )
    return output.getvalue()


def export_balances(session: Session, **filters) -> bytes:
    # A single SELECT provides one consistent PostgreSQL statement snapshot.
    query = item_query(session, **filters).add_columns(Manufacturer.name, InventoryCategory.name)
    query = (
        query.join(Manufacturer, Manufacturer.id == InventoryItem.manufacturer_id)
        .join(
            InventoryCategory,
            InventoryCategory.id == InventoryItem.category_id,
        )
        .limit(MAX_EXPORT_ROWS + 1)
    )
    rows = [
        [
            item.internal_code,
            item.model,
            item.article,
            manufacturer,
            category,
            int(amount),
            item.min_stock,
            "Да" if item.min_stock > 0 and amount < item.min_stock else "Нет",
            "Да" if item.archived_at else "Нет",
        ]
        for item, amount, manufacturer, category in session.execute(query)
    ]
    return workbook(
        "Остатки",
        [
            "Код",
            "Модель",
            "Артикул",
            "Производитель",
            "Категория",
            "Остаток, шт.",
            "Минимум, шт.",
            "Дефицит",
            "В архиве",
        ],
        rows,
    )


def export_movements(
    session: Session,
    *,
    item_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
    document_type: str | None = None,
    recipient_employee_id: uuid.UUID | None = None,
) -> bytes:
    if date_from and date_to and date_from > date_to:
        fail(422, "invalid_date_range", "Начало периода должно быть не позднее окончания.")
    query = select(InventoryMovement, InventoryDocumentItem, InventoryDocument, User.display_name)
    query = query.join(
        InventoryDocumentItem, InventoryDocumentItem.id == InventoryMovement.document_item_id
    )
    query = query.join(InventoryDocument, InventoryDocument.id == InventoryDocumentItem.document_id)
    query = query.join(User, User.id == InventoryDocument.created_by_id)
    if item_id:
        query = query.where(InventoryMovement.inventory_item_id == item_id)
    if date_from:
        query = query.where(InventoryDocument.document_date >= date_from)
    if date_to:
        query = query.where(InventoryDocument.document_date <= date_to)
    if document_type:
        query = query.where(InventoryDocument.document_type == document_type)
    if recipient_employee_id:
        query = query.where(InventoryDocument.recipient_employee_id == recipient_employee_id)
    query = query.order_by(InventoryMovement.occurred_at, InventoryMovement.id).limit(
        MAX_EXPORT_ROWS + 1
    )
    rows = [
        [
            document.number,
            KINDS[document.document_type],
            document.document_date.isoformat(),
            movement.occurred_at.astimezone(ZoneInfo("Asia/Yekaterinburg")).isoformat(),
            line.internal_code,
            line.model,
            line.manufacturer,
            movement.delta,
            document.recipient_name,
            document.recipient_department,
            operator,
            str(document.reversal_of_id) if document.reversal_of_id else "",
            document.reason,
            document.supplier_name,
            document.recipient_room,
        ]
        for movement, line, document, operator in session.execute(query)
    ]
    return workbook(
        "Движения",
        [
            "Документ",
            "Тип",
            "Дата документа",
            "Проведено (UTC+05:00)",
            "Код",
            "Модель (снимок)",
            "Производитель (снимок)",
            "Изменение, шт.",
            "Получатель (снимок)",
            "Подразделение (снимок)",
            "Оператор",
            "Отмена документа UUID",
            "Причина отмены",
            "Поставщик (снимок)",
            "Кабинет (снимок)",
        ],
        rows,
    )
