import argparse
import json
from pathlib import Path
import streamlit as st

def get_file_name(conv_type: str, task: str, model: str):
    file_name = f"{conv_type}_{task}_{model}.jsonl"
    return file_name.replace("/", "_")


def load_conversations(file_path: Path):
    conversations = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            conversations.append(json.loads(line))

    return conversations

def save_annotations(annotations, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for annotation in annotations:
            f.write(json.dumps(annotation, ensure_ascii=False) + "\n")

def load_annotations(file_path: Path):
    if not file_path.exists():
        return []

    annotations = []

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            annotations.append(json.loads(line))

    return annotations

content_component = st.components.v2.component(
    name="content_viewer",
    html='<div id="content" style="white-space: pre-wrap;"></div>',
    js="""
    function escapeHtml(text) {
        return text.replace(/[&<>"']/g, c => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        })[c]);
    }

    export default function(component) {
        const { data, parentElement, setStateValue } = component;

        const el = parentElement.querySelector("#content");

        // 保存済みアノテーションをハイライト
        const annotations = [...data.annotations].sort(
            (a, b) => a.start - b.start
        );

        let html = "";
        let current = 0;

        for (const a of annotations) {
            html += escapeHtml(data.content.slice(current, a.start));

            const color = a.source === "user" ? "#b3e5fc" : "#ffccbc";

            html += `<span style="background-color: ${color};"
                            title="${a.source}">${escapeHtml(
                                data.content.slice(a.start, a.end)
                            )}</span>`;

            current = a.end;
        }

        html += escapeHtml(data.content.slice(current));
        el.innerHTML = html;

        // 範囲選択
        el.addEventListener("mouseup", () => {
            const root = el.getRootNode();
            const selection = root.getSelection();

            if (!selection || selection.isCollapsed) return;

            const range = selection.getRangeAt(0);

            const preRange = document.createRange();
            preRange.selectNodeContents(el);
            preRange.setEnd(range.startContainer, range.startOffset);

            const start = preRange.toString().length;
            const end = start + selection.toString().length;

            setStateValue("selection", {
                text: selection.toString(),
                start: start,
                end: end
            });
        });
    }
    """
)


def show_conversation(data: dict):
    if "annotations" not in st.session_state:
        st.session_state.annotations = []

    conversation_id = data["conv_id"]

    for message_id, message in enumerate(data["trace"]):
        if message["role"] == "log":
            continue

        role = message["role"]
        content = message["content"]

        # メッセージに紐づくアノテーション
        annotations = [
            a for a in st.session_state.annotations
            if a["conversation_id"] == conversation_id
            and a["message_id"] == message_id
        ]

        with st.chat_message(role):
            st.write(f"**{role}**")

            result = content_component(
                data={"content": content, "annotations": annotations},
                key=f"content_{conversation_id}_{message_id}"
            )

            # 新規アノテーション
            if result and (selection := result.get("selection")):
                st.write(f"選択文字列: {selection['text']}")
                st.write(f"Position: {selection['start']} - {selection['end']}")

                source = st.radio(
                    "Source",
                    ["user", "assistant"],
                    horizontal=True,
                    key=f"source_{conversation_id}_{message_id}"
                )

                if st.button("保存", key=f"save_{conversation_id}_{message_id}"):
                    st.session_state.annotations.append({
                        "conversation_id": conversation_id,
                        "message_id": message_id,
                        **selection,
                        "source": source,
                    })
                    st.rerun()

            # 保存済みアノテーションの編集
            for i, annotation in enumerate(annotations):
                with st.container(border=True):
                    st.write(f"**{annotation['text']}**")
                    st.caption(
                        f"Position: {annotation['start']} - {annotation['end']}"
                    )

                    source = st.radio(
                        "Source",
                        ["user", "assistant"],
                        index=["user", "assistant"].index(annotation["source"]),
                        horizontal=True,
                        key=f"edit_source_{conversation_id}_{message_id}_{i}"
                    )

                    col1, col2 = st.columns(2)

                    if col1.button("更新", key=f"update_{conversation_id}_{message_id}_{i}"):
                        annotation["source"] = source
                        st.rerun()

                    if col2.button("削除", key=f"delete_{conversation_id}_{message_id}_{i}"):
                        st.session_state.annotations.remove(annotation)
                        st.rerun()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=str, default="math")
    parser.add_argument("--conv_type", type=str, default="sharded")
    parser.add_argument("--model", type=str, default="Qwen/Qwen3.5-9B")
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    project_root_path = script_path.parent.parent.parent
    output_path = script_path.parent / "annotations.jsonl"
    file_name = get_file_name(args.conv_type, args.task, args.model)
    log_file_path = (
        project_root_path / "logs" / args.task / args.conv_type / file_name
    )

    conversations = load_conversations(log_file_path)

    if not conversations:
        st.warning("No conversations found.")
        return

    if "current_index" not in st.session_state:
        st.session_state.current_index = 0

    if "annotations" not in st.session_state:
        st.session_state.annotations = load_annotations(output_path)

    # Header
    st.title("Conversation Viewer")

    current_index = st.session_state.current_index
    total = len(conversations)

    st.write(f"Conversation {current_index + 1} / {total}")

    # Navigation
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button("← Previous", disabled=current_index == 0):
            st.session_state.current_index -= 1
            st.rerun()

    with col3:
        if st.button("Next →", disabled=current_index == total - 1):
            st.session_state.current_index += 1
            st.rerun()

    # Conversation
    data = conversations[current_index]

    st.divider()
    show_conversation(data)

    if st.button("Export JSONL"):
        save_annotations(
            st.session_state.annotations,
            output_path
        )
        st.success("Saved annotations.jsonl")


if __name__ == "__main__":
    main()