"use client";

import React, { use, useEffect, useState } from 'react';
import { ConversationsList } from '@/components/projects/ConversationsList';
import { KnowledgeBaseSidebar } from '@/components/projects/KnowledgeBaseSidebar';
import { FileDetailsModal } from '@/components/projects/FileDetailsModal';
import { useAuth } from '@clerk/nextjs';
import { apiClient } from '@/lib/api';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { NotFound } from '@/components/ui/NotFound';
import toast from "react-hot-toast";
import { Users } from 'lucide-react';
import { Project, ProjectDocument, ProjectSettings, Chat} from "@/lib/types"


interface ProjectPageProps {
    params: Promise<{
        projectId: string
    }>;
}

interface ProjectData {
    project: Project | null;
    chats: Chat[];
    documents: ProjectDocument[];
    settings: ProjectSettings | null;
}

function ProjectPage({params}: ProjectPageProps) {
    // params is not a direct object it is a js promise, we have to resolve the promise to get the object
    // the "use" hook helps in resolving the promise and provide the object
    const {projectId} = use(params);
    const {getToken, userId} = useAuth();
    //data state
    const [data,setData] = useState<ProjectData>({
        project:null,
        chats:[],
        documents:[],
        settings:null
    })

    const [loading,setLoading] = useState(true);
    const [error, setError] = useState<string|null>(null);
    const [isCreatingChat, setIsCreatingChat] = useState(false);

    // UI states
    const [activeTab, setActiveTab] = useState<"documents" | "settings">("documents");
    const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
    
    //load all data
    useEffect(()=>{
        const loadAllData = async () => {
            if(!userId) return;
            try{
                setLoading(true);
                setError(null);
                const token = await getToken();
                // 4 API calls
                const [projectRes, chatsRes, documentRes, settingsRes] = await Promise.all([
                    apiClient.get(`/api/projects/${projectId}`,token),
                    apiClient.get(`/api/projects/${projectId}/chats`,token),
                    apiClient.get(`/api/projects/${projectId}/files`,token),
                    apiClient.get(`/api/projects/${projectId}/settings`,token)
                ])
                setData({
                    project: projectRes.data,
                    chats: chatsRes.data,
                    documents: documentRes.data,
                    settings: settingsRes.data
                })
            } catch(err) {
                setError('Failed to fetch data')
                console.error("Failed to fetch data", err);
                toast.error("Failed to create project");

            } finally {
                setLoading(false);
            }
        };
        loadAllData();
    },[userId, projectId])

    // chat related methods
    const handleCreateNewChat = async () => {
        if(!userId) return;
        try{
            setIsCreatingChat(true);
            const token = await getToken();
            const chatNumber = Date.now() % 1000
            const result = await apiClient.post("/api/chats",{
                title: `Chat #${chatNumber}`,
                project_id: projectId
            },
            token)
            const savedChat = result.data;
            setData((prev)=>({
                ...prev,
                chats: [savedChat, ...prev.chats]
            }))
            toast.success('Chat created successfully')
        } catch(err) {
            console.error("Failed to create chat", err);
            toast.error("Failed to create chat")
        } finally {
            setIsCreatingChat(false);
        }
    };
    const handleDeleteChat = async (chatId: string) => {
        if(!userId) return 
        try{
            const token = await getToken()
            await apiClient.delete(`/api/chats/${chatId}`,token);
            setData((prev)=>({
                ...prev,
                chats: prev.chats.filter((chat)=> chat.id !== chatId)
            }))
            toast.success("Chat deleted successfully");
        } catch(err) {
            toast.error("Failed to delete chat")
        }
    };
    const handleChatClick = (chatId: string) => {
        console.log("Navigate to chat:",chatId);
    };

    // document related methods
    const handleDocumentUpload = async (files: File[]) => {
        console.log('Upload files',files)
    };

    const handleDocumentDelete = async (documentId: string) => {
        console.log("Document deleted");
    };
    const handleOpenDocument = (documentId: string) => {
        console.log("Open document: ",documentId);
        setSelectedDocumentId(documentId);
    };
    // website url
    const handleUrlAdd = async (url:string) => {
        console.log("Add url: ",url);
    }


    // project settings
    const handleDraftSettings = (updates: any) => {
        console.log("Update local state with draft settings:",updates);
        setData((prev)=>{
            if(!prev.settings){
                console.warn("Cannot update settings: not loaded")
                return prev
            }
            return{
                ...prev,
                settings:{
                    ...prev.settings,
                    ...updates
                }  
            }
        })

    }

    const handlePublishSettings = async () => {
        if(!userId || !data.settings){
            toast.error("Cannot save settings")
        }
        try {
            const token = await getToken()
            const result = await apiClient.put(`/api/projects/${projectId}/settings`,data.settings,token)
            setData((prev)=>({
                ...prev,
                settings: result.data
            }))

            toast.success('Settings saved successfully')
        } catch(err) {
            toast.error("Failed to save settings")
        }
    }

    const selectedDocument = selectedDocumentId ? data.documents.find((doc) => doc.id == selectedDocumentId): null
    if (loading){
        return <LoadingSpinner message='Loading Project'/>
    }
    if (!data.project){
        return <NotFound message='Project Not Found'/>
    }
    return (
        <>
            <div>
                <div className='flex h-screen bg-[#0d1117] gap-4 p-4'>
                    <ConversationsList
                        project={data.project}
                        conversations={data.chats}
                        error={error}
                        loading={isCreatingChat}
                        onCreateNewChat={handleCreateNewChat}
                        onChatClick={handleChatClick}
                        onDeleteChat={handleDeleteChat}
                    />
                    <KnowledgeBaseSidebar
                        activeTab={activeTab}
                        onSetActiveTab={setActiveTab}
                        projectDocuments={data.documents}
                        onDocumentUpload={handleDocumentUpload}
                        onDocumentDelete={handleDocumentDelete}
                        onOpenDocument={handleOpenDocument}
                        onUrlAdd={handleUrlAdd}
                        projectSettings={data.settings}
                        settingsError={null}
                        settingsLoading={false}
                        onUpdateSettings={handleDraftSettings}
                        onApplySettings={handlePublishSettings}
                    />
                </div>
            </div>
            {selectedDocumentId && 
                <FileDetailsModal 
                    document={selectedDocument}
                    onClose={()=>setSelectedDocumentId(null)}
                />
            }
        </>
    )
}

export default ProjectPage;