import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Field, Notice, ErrorState } from '../../components/common';
import { Button } from '../../components/ui/button';
import { Input, Select } from '../../components/ui/input';
import { request } from '../../lib/api';
import { useOptions } from './api';
import type { Manufacturer, Category } from './types';

export function ReferenceSelect({kind,value,initialName,disabled,onChange}:{kind:'categories'|'manufacturers';value:string;initialName?:string;disabled:boolean;onChange:(id:string)=>void}) {
  const category=kind==='categories';
  const [search,setSearch]=useState('');
  const query=useOptions<Manufacturer | Category>(`/inventory/${kind}`,search);
  const client=useQueryClient();
  const [selected,setSelected]=useState<{id:string;name:string}|undefined>(value?{id:value,name:initialName??''}:undefined);
  const [create,setCreate]=useState(false);
  const [name,setName]=useState('');const [code,setCode]=useState('');
  const [error,setError]=useState('');const [pending,setPending]=useState(false);
  async function save(){
    setError('');
    if(!name.trim() || category&&!/^[a-z0-9][a-z0-9_-]*$/i.test(code.trim())){setError(category?'Укажите название и код категории: латинские буквы, цифры, дефис или подчёркивание.':'Укажите название производителя.');return;}
    setPending(true);
    try{
      const result=await request<Manufacturer|Category>(`/inventory/${kind}`,{method:'POST',body:{name:name.trim(),...(category?{code:code.trim().toLowerCase()}:{})}});
      setSelected(result);onChange(result.id);setSearch('');setCreate(false);setName('');setCode('');
      await client.invalidateQueries({queryKey:['warehouse','options',`/inventory/${kind}`]});
    }catch(error){setError((error as Error).message);}finally{setPending(false);}
  }
  return <div className="space-y-3">
    {!category&&<Field label="Поиск производителя">{id=><Input id={id} maxLength={100} value={search} disabled={disabled||pending} placeholder="Введите название" onChange={event=>setSearch(event.target.value)}/>}</Field>}
    <Field label={category?'Категория':'Производитель'}>{id=><Select id={id} required disabled={disabled||pending||query.isPending&&!value} value={value} onChange={event=>{const next=query.data?.find(option=>option.id===event.target.value);setSelected(next);onChange(event.target.value);}}>
      <option value="">{category?'Выберите категорию':'Выберите производителя'}</option>
      {selected&&selected.id===value&&!query.data?.some(option=>option.id===value)&&<option value={selected.id}>{selected.name}{!search&&query.data&&selected.id===value&&selected.name===initialName?' (архив)':''}</option>}
      {query.data?.map(option=><option key={option.id} value={option.id}>{option.name}</option>)}
    </Select>}</Field>
    {query.isPending&&<p role="status" className="text-xs text-muted">Загружаем справочник…</p>}
    {query.error&&<ErrorState error={query.error} onRetry={()=>void query.refetch()}/>}
    {query.data?.length===0&&<p className="text-sm text-muted">{search?'По этому запросу записей нет.':'В справочнике нет активных записей. Добавьте первую.'}</p>}
    <Button type="button" variant="outline" disabled={disabled||pending} onClick={()=>{setCreate(!create);setError('');}}>{create?'Отменить добавление':category?'Добавить категорию':'Добавить производителя'}</Button>
    {create&&<div className="space-y-3 rounded-lg border border-border p-3">
      {error&&<Notice>{error}</Notice>}
      {category&&<Field label="Код новой категории" hint="Латинские буквы, цифры, дефис или подчёркивание. Код нельзя изменить после создания.">{id=><Input id={id} maxLength={50} disabled={disabled||pending} value={code} onChange={event=>setCode(event.target.value)}/>}</Field>}
      <Field label={category?'Название новой категории':'Название нового производителя'}>{id=><Input id={id} maxLength={200} disabled={disabled||pending} value={name} onChange={event=>setName(event.target.value)}/>}</Field>
      <Button type="button" disabled={disabled||pending} onClick={()=>void save()}>{pending?'Сохраняем…':category?'Сохранить категорию':'Сохранить производителя'}</Button>
    </div>}
  </div>;
}
