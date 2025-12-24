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
import { useRouter } from 'next/navigation';

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
    const router = useRouter();
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

    useEffect(() => {
        // .some() checks if at least one element in the array satisfies a condition
        const hasProcessingDocuments = data.documents.some(
            (doc) => 
                doc.processing_status && !["completed","failed"].includes(doc.processing_status)
        )
         if (!hasProcessingDocuments) {
            return;
         }
         //setInterval(function, interval_time) , 2000 = 2secs
         const pollInterval = setInterval(async () => {
            try {
                const token = await getToken();
                const documentsRes = await apiClient.get(
                    `/api/projects/${projectId}/files`,
                    token
                )
                setData((prev) => ({
                    ...prev,
                    documents: documentsRes.data
                }));
            } catch (err) {
               console.error("Polling error:", err);
            }
         }, 2000)
         return () => clearInterval(pollInterval);
    },[data.documents,projectId, getToken])
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
        router.push(`/projects/${projectId}/chats/${chatId}`);
    };

    // document related methods
    const handleDocumentUpload = async (files: File[]) => {
        if(!userId) return;
        const token = await getToken();
        //Process all files in parallel
        const uploadedDocuments : ProjectDocument[] = [];
        const uploadPromises = files.map(async(file)=>{
            try{
                console.log('file:',file);
                // 1. get presigned urls
                const uploadData = await apiClient.post(`/api/projects/${projectId}/files/upload-url`, {
                    filename:file.name,
                    file_size: file.size,
                    file_type: file.type
                }, token)

                const {upload_url,s3_key} = uploadData.data
                // 2. upload the file directly to s3 using the presigned url
                await apiClient.uploadToS3(upload_url, file);
                // 3. confirm upload to server to change the processing status of a document from 'uploading' to failed or completed
                const updatedDocument = await apiClient.post(
                    `/api/projects/${projectId}/files/confirm`,
                    {
                        s3_key
                    },
                    token
                );

                uploadedDocuments.push(updatedDocument.data);
            } catch (err) {
                toast.error(`Failed to upload ${file.name}`)
            }
        })
        //we move on to next step only after all the api calls are settled.
        await Promise.allSettled(uploadPromises);

        //Update the local state with uploaded documents
        if (uploadedDocuments.length>0){
            setData((prev)=>({
                ...prev,
                documents:[...uploadedDocuments, ...prev.documents]
            }));
            toast.success(`${uploadedDocuments.length} file(s) uploaded`)
        }
    };

    const handleDocumentDelete = async (documentId: string) => {
        if(!userId) return;
        try {
            const token = await getToken()
            await apiClient.delete(
                `/api/projects/${projectId}/files/${documentId}`, token
            );
            setData((prev)=>({
                ...prev,
                documents: prev.documents.filter((doc)=> doc.id!==documentId)
            }))
            toast.success("Document deleted successfully")
        } catch (err) {
            toast.error("Document deletion failed")
        }
    };
    const handleOpenDocument = (documentId: string) => {
        console.log("Open document: ",documentId);
        setSelectedDocumentId(documentId);
    };
    // website url
    const handleUrlAdd = async (url:string) => {
        if(!userId) return;
        try{
            const token = await getToken()
            const result = await apiClient.post(`/api/projects/${projectId}/urls`,
                {
                    url
                },
                token
            )
            const newDocument = result.data;
            setData((prev)=>({
                ...prev,
                documents:[newDocument, ...prev.documents]
            }))
            toast.success('Website added successfully');
            console.log(result);
        } catch(err) { 
            toast.error('Failed to add website');
        }
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