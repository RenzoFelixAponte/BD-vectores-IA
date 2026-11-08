import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, X } from "lucide-react";

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "warning";
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "danger",
  onConfirm,
  onCancel,
}: Props) {
  const accent = variant === "danger" ? "text-red-400" : "text-amber-400";
  const btnClass =
    variant === "danger"
      ? "bg-red-600 hover:bg-red-500"
      : "bg-amber-600 hover:bg-amber-500";

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onCancel}
          />

          {/* Dialog */}
          <motion.div
            key="dialog"
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            initial={{ opacity: 0, scale: 0.92, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.92, y: 8 }}
            transition={{ type: "spring", stiffness: 380, damping: 30 }}
          >
            <div className="w-full max-w-sm bg-slate-800 border border-slate-700 rounded-xl shadow-2xl overflow-hidden">
              {/* Header */}
              <div className="flex items-start justify-between p-5 pb-3">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-lg bg-slate-700/60 ${accent}`}>
                    <AlertTriangle size={18} />
                  </div>
                  <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
                </div>
                <button
                  onClick={onCancel}
                  className="p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-slate-700 transition-colors"
                >
                  <X size={15} />
                </button>
              </div>

              {/* Body */}
              <p className="px-5 pb-5 text-sm text-slate-400 leading-relaxed">{message}</p>

              {/* Divider */}
              <div className="border-t border-slate-700" />

              {/* Actions */}
              <div className="flex justify-end gap-2 px-5 py-3">
                <button
                  onClick={onCancel}
                  className="px-3.5 py-1.5 text-sm rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-700 transition-colors"
                >
                  {cancelLabel}
                </button>
                <button
                  onClick={onConfirm}
                  className={`px-3.5 py-1.5 text-sm rounded-lg text-white font-medium transition-colors ${btnClass}`}
                >
                  {confirmLabel}
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
