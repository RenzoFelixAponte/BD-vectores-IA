import { ImageOff } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";

interface Props {
  path: unknown;
  alt: string;
  className?: string;
}

export function ProductImage({ path, alt, className = "" }: Props) {
  const [failed, setFailed] = useState(false);
  const hasPath = typeof path === "string" && path.trim().length > 0;

  if (!hasPath || failed) {
    return (
      <div className={`flex items-center justify-center bg-slate-800 text-slate-500 ${className}`}>
        <ImageOff size={28} />
      </div>
    );
  }

  return (
    <img
      src={api.imageUrl(path)}
      alt={alt}
      className={`object-cover bg-slate-800 ${className}`}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
