import { useState, useEffect } from "react";
import { X } from "lucide-react";
import { DetailInspector } from "../projects/document-details/DetailInspector";
import { apiClient } from "@/lib/api"; // adjust import
import { useAuth } from "@clerk/nextjs";

interface CitationModalProps {
  isOpen: boolean;
  onClose: () => void;
  documentId: string | number | null; // new prop
  chunkId: string | number | null; // new prop
  projectId: string | number | null; // new prop
}

export function CitationModal({ isOpen, onClose, documentId, chunkId, projectId }: CitationModalProps) {
  const [chunk, setChunk] = useState<any | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const {getToken, userId} = useAuth() 

  // Fetch chunk when modal opens AND chunkId changes
  useEffect(() => {
    if (isOpen && chunkId && documentId) {
      const fetchChunk = async () => {
        setIsLoading(true);
        try {
          const token = await getToken();
          const result = await apiClient.get(
            `/api/projects/${projectId}/documents/${documentId}/chunks/${chunkId}`,
            token
          );
          console.log("result from getchunk:", result);
          setChunk(result.data);
        } catch (err) {
          console.error("Failed to fetch chunk:", err);
          setChunk(null);
        } finally {
          setIsLoading(false);
        }
      };

      fetchChunk();
    } else {
      setChunk(null);
    }
  }, [isOpen, chunkId, documentId]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
  <div className="bg-[#1e1e1e] w-[80vw] h-[80vh] rounded-lg shadow-lg flex overflow-hidden">
    {/* Left Pane: Chunk Preview */}
    <div className="flex-1 overflow-auto p-4">
      {/* Header */}
      <div className="flex justify-between items-center mb-4">
        <h4 className="text-gray-100 font-medium">Citation Details</h4>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-200">
          <X size={20} />
        </button>
      </div>

      {/* Chunk Content */}
      {isLoading ? (
        <p className="text-gray-400">Loading chunk...</p>
      ) : chunk ? (
        <div className="p-4 border rounded-lg bg-[#2a2a2a] mb-4">
          <div className="flex items-start justify-between mb-2">
            <div className="flex items-center gap-2">
              {Array.isArray(chunk.type) &&
                chunk.type.map((type: string) => (
                  <span
                    key={type}
                    className={`px-2 py-1 rounded text-xs font-medium ${
                      type === "text"
                        ? "bg-green-500/20 text-green-400 border border-green-500/30"
                        : type === "image"
                        ? "bg-purple-500/20 text-purple-400 border border-purple-500/30"
                        : "bg-orange-500/20 text-orange-400 border border-orange-500/30"
                    }`}
                  >
                    {type.toUpperCase()}
                  </span>
                ))}
              <span className="text-sm text-gray-400">Page {chunk.page_number}</span>
            </div>
            <div className="text-sm text-gray-400">{chunk.char_count} chars</div>
          </div>
          <p className="text-sm text-gray-300">{chunk.content}</p>
        </div>
      ) : (
        <p className="text-gray-400">Chunk not found</p>
      )}
    </div>

    {/* Right Pane: Detail Inspector */}
    <div className="w-[40%] h-full border-l border-gray-700 flex flex-col">
      <DetailInspector
        classDetail=""
        selectedChunk={chunk}
        isProcessingComplete={!isLoading}
      />
    </div>
  </div>
</div>

  );
}
