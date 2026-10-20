import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import { ItemForm } from '../features/inventory/ItemForm';
import { Photos } from '../features/inventory/Photos';

let calls: {path:string; options?:RequestInit}[];
let failUpload: boolean;
const saved = {id:'item1',version:1,internal_code:'NEW',model:'Модель'};
beforeEach(()=>{
  calls=[];failUpload=false;
  vi.stubGlobal('fetch',vi.fn(async(path:string,options?:RequestInit)=>{
    calls.push({path,options});
    if(path.endsWith('/auth/csrf'))return Response.json({csrf_token:'csrf'});
    if(path.endsWith('/manufacturers')&&options?.method==='POST')return Response.json({id:'new-maker',name:'Новый производитель'});
    if(path.endsWith('/categories')&&options?.method==='POST')return Response.json({id:'new-category',name:'Кабели',code:'cables'});
    if(path.includes('/photos')&&options?.method==='POST')return failUpload?Response.json({detail:{code:'invalid_photo',message:'Повреждённое фото'}},{status:422}):Response.json({id:'photo'});
    if(path.endsWith('/items')&&options?.method==='POST')return Response.json(saved);
    if(path.includes('/manufacturers?'))return Response.json({items:[{id:'maker',name:'Производитель'}],total:1});
    if(path.includes('/categories?'))return Response.json({items:[{id:'category',name:'Картриджи'}],total:1});
    return Response.json({items:[],total:0});
  }));
  URL.createObjectURL=vi.fn(()=> 'blob:preview');URL.revokeObjectURL=vi.fn();
});
function show(children:React.ReactNode){render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{children}</QueryClientProvider>);}
async function fill(){const events=userEvent.setup();await events.type(screen.getByLabelText('Внутренний код'),'NEW');await events.selectOptions(screen.getByLabelText('Категория'),'category');await events.selectOptions(screen.getByLabelText('Производитель'),'maker');await events.type(screen.getByLabelText('Модель расходника'),'Модель');return events;}
it('создаёт справочники внутри карточки и сразу выбирает новые значения',async()=>{
  show(<ItemForm onClose={()=>{}} onSaved={()=>{}}/>);const events=userEvent.setup();
  await events.click(await screen.findByRole('button',{name:'Добавить категорию'}));
  await events.type(screen.getByLabelText('Код новой категории'),'cables');await events.type(screen.getByLabelText('Название новой категории'),'Кабели');
  await events.click(screen.getByRole('button',{name:'Сохранить категорию'}));
  await waitFor(()=>expect(screen.getByLabelText('Категория')).toHaveValue('new-category'));
  await events.click(screen.getByRole('button',{name:'Добавить производителя'}));
  await events.type(screen.getByLabelText('Название нового производителя'),'Новый производитель');
  await events.click(screen.getByRole('button',{name:'Сохранить производителя'}));
  await waitFor(()=>expect(screen.getByLabelText('Производитель')).toHaveValue('new-maker'));
  await events.type(screen.getByLabelText('Поиск производителя'),'нов');
  await waitFor(()=>expect(calls.some(call=>call.path.includes('q=%D0%BD%D0%BE%D0%B2'))).toBe(true));
  expect(screen.getByLabelText('Производитель')).toHaveValue('new-maker');
});
it('показывает два предварительных фото и сохраняет их после создания позиции',async()=>{
  const onSaved=vi.fn();show(<ItemForm onClose={()=>{}} onSaved={onSaved}/>);const events=await fill();
  await events.upload(screen.getByLabelText('Загрузить фото'),[new File(['a'],'a.png',{type:'image/png'}),new File(['b'],'b.png',{type:'image/png'})]);
  expect(screen.getAllByRole('img',{name:/Предпросмотр/})).toHaveLength(2);
  expect(calls.filter(call=>call.options?.method==='POST')).toHaveLength(0);
  await events.click(screen.getByRole('button',{name:'Сохранить позицию'}));
  await waitFor(()=>expect(onSaved).toHaveBeenCalled());
  expect(calls.filter(call=>call.path.endsWith('/items/item1/photos')&&call.options?.method==='POST')).toHaveLength(2);
});
it('повтор после отказа фото не создаёт вторую позицию',async()=>{
  const onSaved=vi.fn();show(<ItemForm onClose={()=>{}} onSaved={onSaved}/>);const events=await fill();
  await events.upload(screen.getByLabelText('Загрузить фото'),new File(['a'],'a.png',{type:'image/png'}));failUpload=true;
  await events.click(screen.getByRole('button',{name:'Сохранить позицию'}));await screen.findByText(/Повреждённое фото/);
  expect(onSaved).not.toHaveBeenCalled();failUpload=false;
  await events.click(screen.getByRole('button',{name:'Повторить загрузку фото'}));await waitFor(()=>expect(onSaved).toHaveBeenCalled());
  expect(calls.filter(call=>call.path.endsWith('/items')&&call.options?.method==='POST')).toHaveLength(1);
});
it('ограничивает количество, тип и размер файлов до загрузки',async()=>{
  show(<Photos itemId="item1" manage/>);const events=userEvent.setup({applyAccept:false});const input=await screen.findByLabelText('Загрузить фото');
  await events.upload(input,new File(['x'],'file.txt',{type:'text/plain'}));await screen.findByText(/Только JPEG, PNG или WebP/);
  await events.upload(input,new File([new Uint8Array(5*1024*1024+1)],'large.png',{type:'image/png'}));await screen.findByText(/превышает 5 МБ/);
  await events.upload(input,Array.from({length:6},(_,i)=>new File(['x'],`${i}.png`,{type:'image/png'})));await screen.findByText(/Не более 5 фотографий/);
  expect(calls.some(call=>call.options?.method==='POST')).toBe(false);
});
