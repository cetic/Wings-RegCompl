import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(__file__).parent / "schemas" / "provision_package.schema.json"
STATEMENT_ID = re.compile(r"^[a-z0-9-]+:st\.[A-Za-z0-9_.-]+$")
QUESTION_ID = re.compile(r"^[a-z0-9-]+:q\.[a-z0-9-]+$")
NUMBER_WORDS = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
}
REQUIRED_MODALITY = {
    "Obligation": "shall",
    "Prohibition": "shall_not",
    "Permission": "may",
    "Recommendation": "should",
    "LegalEffect": "deemed",
}


@lru_cache(maxsize=1)
def package_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def normalize_evidence(value: str) -> str:
    value = unicodedata.normalize("NFKC", value.replace("\u00ad", ""))
    value = value.translate(str.maketrans("‘’“”–—", "''\"\"--"))
    return " ".join(value.split()).casefold()


def _condition_question_ids(condition: Any) -> set[str]:
    if not isinstance(condition, dict):
        return set()
    if "q" in condition and isinstance(condition["q"], str):
        return {condition["q"]}
    question_ids: set[str] = set()
    for key in ("all", "any"):
        for child in condition.get(key, []):
            question_ids.update(_condition_question_ids(child))
    question_ids.update(_condition_question_ids(condition.get("not")))
    return question_ids


def _condition_edges(condition: Any) -> set[str]:
    return _condition_question_ids(condition)


def _has_question_cycle(questions: list[dict[str, Any]]) -> bool:
    dependencies = {
        question["id"]: _condition_edges(question.get("askIf")) for question in questions
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(question_id: str) -> bool:
        if question_id in visiting:
            return True
        if question_id in visited:
            return False
        visiting.add(question_id)
        if any(visit(child) for child in dependencies.get(question_id, set())):
            return True
        visiting.remove(question_id)
        visited.add(question_id)
        return False

    return any(visit(question_id) for question_id in dependencies)


def _duration_numbers(duration: str) -> list[str]:
    return re.findall(r"\d+", duration)


def _operator_errors(
    condition: Any,
    questions: dict[str, dict[str, Any]],
    path: str,
) -> list[str]:
    allowed_operators = {
        "boolean": {"is_true", "is_false", "eq", "neq"},
        "single_choice": {"eq", "neq", "in", "not_in"},
        "multi_choice": {"contains", "in", "not_in"},
        "number": {"eq", "neq", "gte", "lte", "gt", "lt"},
        "date": {"eq", "neq", "gte", "lte", "gt", "lt"},
    }
    errors: list[str] = []
    for leaf in _condition_leaves(condition):
        question_id = str(leaf.get("q", ""))
        question = questions.get(question_id)
        if question is None:
            continue
        answer_type = str(question.get("answerType", ""))
        if leaf.get("op") not in allowed_operators.get(answer_type, set()):
            errors.append(f"{path}: operator {leaf.get('op')} is incompatible with {answer_type}")
    return errors


def _number_in_evidence(number: str, evidence: str) -> bool:
    if re.search(rf"(?<!\d){re.escape(number)}(?!\d)", evidence):
        return True
    words = {word for word, value in NUMBER_WORDS.items() if value == number}
    return any(re.search(rf"\b{word}\b", evidence) for word in words)


def validate_package(
    package: dict[str, Any],
    source_provisions: list[dict[str, Any]],
    *,
    catalog_ids: set[str] | None = None,
    catalog_questions: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    errors = [
        f"schema {'.'.join(map(str, error.absolute_path)) or '$'}: {error.message}"
        for error in package_validator().iter_errors(package)
    ]
    if errors:
        return errors

    provision_by_id = {str(node["id"]): node for node in source_provisions}
    package_provisions = {str(node["id"]): node for node in package["provisions"]}
    questions = package["questions"]
    question_ids = {question["id"] for question in questions}
    questions_by_id = {
        **(catalog_questions or {}),
        **{question["id"]: question for question in questions},
    }
    if len(question_ids) != len(questions):
        errors.append("duplicate question id")
    known_ids = catalog_ids or set()
    allowed_ids = known_ids | question_ids
    for group in ("roles", "events", "artefacts", "topicsProposed"):
        allowed_ids.update(str(item["id"]) for item in package.get(group, []))
    statement_ids: set[str] = set()
    statement_prefix = f"{str(package['document']['shortName']).casefold()}:st."
    for statement in package["statements"]:
        statement_id = statement["id"]
        if statement_id in statement_ids:
            errors.append(f"duplicate statement id: {statement_id}")
        statement_ids.add(statement_id)
        if not STATEMENT_ID.fullmatch(statement_id) or not statement_id.startswith(
            statement_prefix
        ):
            errors.append(f"invalid statement id: {statement_id}")
        required_modality = REQUIRED_MODALITY.get(statement["type"])
        if required_modality and statement["modality"] != required_modality:
            errors.append(
                f"{statement_id}: {statement['type']} requires modality {required_modality}"
            )
        derived = [str(item) for item in statement["derivedFrom"]]
        if any(source_id not in package_provisions for source_id in derived):
            errors.append(f"{statement_id}: derivedFrom must refer to a provision in this package")
            continue
        if statement["type"] in {"Obligation", "Prohibition"} and not statement.get("addressees"):
            errors.append(f"{statement_id}: obligations and prohibitions require an addressee")
        evidence = normalize_evidence(statement["evidence"])
        if not any(
            evidence in normalize_evidence(str(provision_by_id.get(source_id, {}).get("text", "")))
            for source_id in derived
        ):
            errors.append(f"{statement_id}: evidence is not verbatim in a derived provision")
        if any(
            not package_provisions[source_id].get("isNormative", False) for source_id in derived
        ):
            errors.append(f"{statement_id}: statements cannot derive from non-normative provisions")
        deadline = statement.get("deadline")
        if deadline:
            duration = str(deadline.get("duration", ""))
            if any(
                not _number_in_evidence(number, evidence) for number in _duration_numbers(duration)
            ):
                errors.append(f"{statement_id}: deadline duration is not supported by its evidence")
        references = set(statement.get("addressees", []))
        for field in (
            "recipients",
            "beneficiaries",
            "triggers",
            "artefacts",
            "procedures",
            "channels",
            "topics",
        ):
            references.update(str(value) for value in statement.get(field, []))
        references.update(_condition_question_ids(statement.get("applicability")))
        errors.extend(
            _operator_errors(statement.get("applicability"), questions_by_id, statement_id)
        )
        missing = references - allowed_ids
        if missing:
            errors.append(
                f"{statement_id}: referenced catalog ids are unknown: {', '.join(sorted(missing))}"
            )

    for question in questions:
        if not QUESTION_ID.fullmatch(question["id"]):
            errors.append(f"invalid question id: {question['id']}")
        if question["source"] not in package_provisions:
            errors.append(f"{question['id']}: source must refer to a provision in this package")
        if question["status"] == "existing" and question["id"] not in known_ids:
            errors.append(f"{question['id']}: existing question is not in the supplied catalog")
        if question["answerType"] in {"single_choice", "multi_choice"} and not question.get(
            "options"
        ):
            errors.append(f"{question['id']}: choice questions require options")
        for dependency_id in _condition_question_ids(question.get("askIf")):
            if dependency_id not in allowed_ids:
                errors.append(
                    f"{question['id']}: askIf references unknown question {dependency_id}"
                )
        errors.extend(_operator_errors(question.get("askIf"), questions_by_id, question["id"]))
    if _has_question_cycle(questions):
        errors.append("questions.askIf contains a dependency cycle")
    for definition in package.get("definitions", []):
        if definition["definedIn"] not in package_provisions:
            errors.append(
                f"{definition['id']}: definedIn must refer to a provision in this package"
            )
    for provision in package["provisions"]:
        applicability = provision.get("applicability")
        errors.extend(_operator_errors(applicability, questions_by_id, str(provision["id"])))
        for question_id in _condition_question_ids(applicability) - allowed_ids:
            errors.append(
                f"{provision['id']} applicability references unknown question {question_id}"
            )
    for question_id in _condition_question_ids(package.get("documentScope")) - allowed_ids:
        errors.append(f"documentScope references unknown question {question_id}")
    errors.extend(_operator_errors(package.get("documentScope"), questions_by_id, "documentScope"))
    return errors


def _condition_leaves(condition: Any) -> list[dict[str, Any]]:
    if not isinstance(condition, dict):
        return []
    if "q" in condition:
        return [condition]
    leaves: list[dict[str, Any]] = []
    for key in ("all", "any"):
        for child in condition.get(key, []):
            leaves.extend(_condition_leaves(child))
    leaves.extend(_condition_leaves(condition.get("not")))
    return leaves
