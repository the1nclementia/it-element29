import { useEffect, useRef, useState } from 'react';
import { Field, Notice } from '../../components/common';
import { Input } from '../../components/ui/input';
import { Button } from '../../components/ui/button';
import { request } from '../../lib/api';

interface PendingPhoto {file:File;url:string;id:string}
export function usePhotoQueue(){
  const [photos,setPhotos]=useState<PendingPhoto[]>([]);
  const current=useRef(photos);current.current=photos;
  useEffect(()=>()=>current.current.forEach(photo=>URL.revokeObjectURL(photo.url)),[]);
  const remove=(id:string)=>setPhotos(previous=>{const removed=previous.find(photo=>photo.id===id);if(removed)URL.revokeObjectURL(removed.url);return previous.filter(photo=>photo.id!==id);});
  function add(files:File[],existing:number){
    if(existing+photos.length+files.length>5)throw new Error('Не более 5 фотографий на позицию. Уберите лишние снимки.');
    for(const file of files){
      if(!['image/jpeg','image/png','image/webp'].includes(file.type))throw new Error('Только JPEG, PNG или WebP. Выберите фотографию поддерживаемого типа.');
      if(file.size>5*1024*1024)throw new Error('Размер фотографии превышает 5 МБ.');
    }
    setPhotos(previous=>[...previous,...files.map(file=>({file,url:URL.createObjectURL(file),id:crypto.randomUUID()}))]);
  }
  async function upload(itemId:string){
    for(const photo of photos){const body=new FormData();body.append('file',photo.file);await request(`/inventory/items/${itemId}/photos`,{method:'POST',body});remove(photo.id);}
  }
  return {photos,add,remove,upload};
}
export function PhotoPicker({queue,existing=0,disabled=false}:{queue:ReturnType<typeof usePhotoQueue>;existing?:number;disabled?:boolean}){
  const [error,setError]=useState('');
  return <div className="space-y-3">
    <Field label="Загрузить фото" hint="JPEG, PNG или WebP; до 5 МБ и 20 Мп, не более 5 фото. Можно выбрать несколько. Снимки загрузятся после сохранения.">{id=><Input id={id} type="file" multiple accept="image/jpeg,image/png,image/webp" disabled={disabled||existing+queue.photos.length>=5} onChange={event=>{setError('');try{queue.add(Array.from(event.target.files??[]),existing);}catch(error){setError((error as Error).message);}event.target.value='';}}/>}</Field>
    {error&&<Notice>{error}</Notice>}
    <div className="grid grid-cols-2 gap-3">{queue.photos.map(photo=><figure key={photo.id} className="min-w-0 space-y-2 rounded-lg border border-border p-2"><img className="h-28 w-full object-contain" src={photo.url} alt={`Предпросмотр ${photo.file.name}`}/><figcaption className="break-all text-xs text-muted">{photo.file.name}</figcaption><Button type="button" size="sm" variant="outline" disabled={disabled} aria-label={`Убрать выбранное фото ${photo.file.name}`} onClick={()=>queue.remove(photo.id)}>Убрать</Button></figure>)}</div>
  </div>;
}
