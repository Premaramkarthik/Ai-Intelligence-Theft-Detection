"use client"

import * as React from "react"
import { useEffect, useState } from "react"
import { AppLayout } from "@/components/shared/AppLayout"
import { fetchApi } from "@/utils/api"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/design-system/Core/Table"
import { Badge } from "@/components/design-system/Core/Badge"
import { Button } from "@/components/design-system/Core/Button"
import { Loader } from "@/components/design-system/Core/Loader"
import { Flex } from "@/components/design-system/Layout/Primitives"
import { Modal } from "@/components/design-system/Core/Modal"
import { Input } from "@/components/design-system/Core/Input"
import { Plus, Trash2, Activity, PlaySquare, VideoOff } from "lucide-react"

export default function CamerasPage() {
  const [cameras, setCameras] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  // Creation Modal State
  const [isAddOpen, setIsAddOpen] = useState(false)
  const [newCamera, setNewCamera] = useState({ name: "", location: "", host: "", port: 554, path: "", stream_type: "rtsp" })
  const [isAdding, setIsAdding] = useState(false)

  const loadCameras = async () => {
    setLoading(true)
    try {
      const data = await fetchApi<any>("/cameras")
      setCameras(Array.isArray(data) ? data : (data.items || []))
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCameras()
  }, [])

  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsAdding(true)
    try {
      await fetchApi("/cameras", {
        method: "POST",
        body: JSON.stringify(newCamera)
      })
      setIsAddOpen(false)
      loadCameras()
    } catch(err) {
      alert("Failed to add camera: " + err)
    } finally {
      setIsAdding(false)
    }
  }

  const handleDelete = async (id: string) => {
    if(!confirm("Are you sure you want to delete this camera?")) return
    try {
      await fetchApi(`/cameras/${id}`, { method: "DELETE" })
      loadCameras()
    } catch(err) {
      alert("Failed to delete.")
    }
  }

  const handleValidate = async (id: string) => {
    try {
      const res = await fetchApi<any>(`/cameras/${id}/validate`, { method: "POST", body: "{}" })
      alert(`Validation result: ${res.is_accessible ? "Accessible" : "Failed"}\nCodec: ${res.codec_name || "Unknown"}\nDimensions: ${res.width}x${res.height}`)
      loadCameras()
    } catch(err) {
      alert("Validation error: " + err)
    }
  }

  const handleToggleInference = async (id: string) => {
    try {
      await fetchApi(`/streams/${id}/inference`, { 
        method: "PATCH", 
        body: JSON.stringify({ enabled: true }) 
      })
      // Just showing success since the camera list might not immediately reflect the live runtime stream state
      alert("Inference triggered. Check the dashboard.")
    } catch(err) {
      alert("Failed to patch inference: " + err)
    }
  }

  return (
    <AppLayout title="Camera Management">
      <div className="w-full max-w-7xl mx-auto space-y-6 animate-in">
        <Flex justify="between" align="center" className="w-full">
          <div>
            <h2 className="text-lg font-semibold text-white">Registered Cameras</h2>
            <p className="text-sm text-neutral-400">Manage surveillance endpoints and inference assignments.</p>
          </div>
          <Button variant="primary" className="gap-2" onClick={() => setIsAddOpen(true)}>
            <Plus size={16} /> Add Camera
          </Button>
        </Flex>

        <div className="rounded-md border border-neutral-800 bg-neutral-900/50">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Status</TableHead>
                <TableHead>Name & Location</TableHead>
                <TableHead>Host/URI</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={4} className="h-32 text-center text-neutral-500">
                    <Flex justify="center" align="center" className="w-full"><Loader size="sm" className="mr-2" /> Loading cameras...</Flex>
                  </TableCell>
                </TableRow>
              ) : cameras.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="h-32 text-center text-neutral-500">
                    No cameras registered yet. Click "Add Camera" to begin.
                  </TableCell>
                </TableRow>
              ) : (
                cameras.map((cam) => (
                  <TableRow key={cam.id}>
                    <TableCell>
                      <Badge variant={cam.status === "active" ? "success" : "default"}>
                        {cam.status || "Unknown"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="font-medium text-white">{cam.name}</div>
                      <div className="text-xs text-neutral-500">{cam.location || "No location set"}</div>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-neutral-400">
                      {cam.direct_rtsp_url || `${cam.host}:${cam.port}${cam.path}`}
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      <Button variant="ghost" size="sm" className="mr-2 text-indigo-400 hover:text-indigo-300" onClick={() => handleToggleInference(cam.id)} title="Trigger Inference stream PATCH">
                        AI <PlaySquare size={16} className="ml-1 inline" />
                      </Button>
                      <Button variant="ghost" size="sm" className="mr-2 text-emerald-500" onClick={() => handleValidate(cam.id)} title="Validate Stream">
                        <Activity size={16} />
                      </Button>
                      <Button variant="danger" size="sm" onClick={() => handleDelete(cam.id)}>
                        <Trash2 size={16} />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <Modal isOpen={isAddOpen} onClose={() => setIsAddOpen(false)} title="Add New Camera">
        <form onSubmit={handleAddSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm text-neutral-300">Camera Name</label>
              <Input required placeholder="Main Entrance" value={newCamera.name} onChange={e => setNewCamera({...newCamera, name: e.target.value})} />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-neutral-300">Location</label>
              <Input placeholder="Lobby" value={newCamera.location} onChange={e => setNewCamera({...newCamera, location: e.target.value})} />
            </div>
          </div>
          <div className="grid grid-cols-[3fr_1fr] gap-4">
            <div className="space-y-2">
              <label className="text-sm text-neutral-300">Host (IP or Domain)</label>
              <Input required placeholder="192.168.1.100" value={newCamera.host} onChange={e => setNewCamera({...newCamera, host: e.target.value})} />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-neutral-300">Port</label>
              <Input type="number" required placeholder="554" value={newCamera.port} onChange={e => setNewCamera({...newCamera, port: parseInt(e.target.value)})} />
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-neutral-300">RTSP Path</label>
            <Input required placeholder="/stream1" value={newCamera.path} onChange={e => setNewCamera({...newCamera, path: e.target.value})} />
          </div>
          <div className="pt-4 flex justify-end space-x-3">
            <Button type="button" variant="ghost" onClick={() => setIsAddOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" disabled={isAdding}>
              {isAdding ? "Adding..." : "Add Camera"}
            </Button>
          </div>
        </form>
      </Modal>
    </AppLayout>
  )
}

