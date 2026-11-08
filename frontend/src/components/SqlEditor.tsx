import Editor from "@monaco-editor/react";
import { Play } from "lucide-react";
import { useRef } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onRun: () => void;
  loading: boolean;
}

export function SqlEditor({ value, onChange, onRun, loading }: Props) {
  const editorRef = useRef<unknown>(null);

  function handleMount(editor: unknown) {
    editorRef.current = editor;
    (editor as { addCommand: (key: number, fn: () => void) => void }).addCommand(2051, onRun);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col border-b border-slate-700">
      {/* Toolbar */}
      <div className="flex shrink-0 items-center justify-between px-3 py-1.5 bg-slate-800 border-b border-slate-700">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">SQL Editor</span>
        <span className="text-[10px] text-slate-500">Ctrl+Enter to run</span>
      </div>

      {/* Monaco */}
      <div className="monaco-wrapper">
        <Editor
          height="100%"
          defaultLanguage="sql"
          theme="vs-dark"
          value={value}
          onChange={(v) => onChange(v ?? "")}
          onMount={handleMount}
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            lineNumbers: "on",
            scrollBeyondLastLine: false,
            wordWrap: "on",
            automaticLayout: true,
            padding: { top: 8, bottom: 8 },
          }}
        />
      </div>

      {/* Run button */}
      <div className="flex shrink-0 items-center gap-3 px-3 py-2 bg-slate-800">
        <button
          onClick={onRun}
          disabled={loading || !value.trim()}
          className="flex items-center gap-2 px-4 py-1.5 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
        >
          {loading
            ? <><span className="spinner" /> Running…</>
            : <><Play size={13} fill="currentColor" /> Run Query</>
          }
        </button>
      </div>
    </div>
  );
}
