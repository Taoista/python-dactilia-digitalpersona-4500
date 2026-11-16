import '@angular/compiler';
import {Component, signal} from '@angular/core';
import {bootstrapApplication} from '@angular/platform-browser';

type Capture = {sequence:number; image:string; hash:string; width:number; height:number; bytes:number};

@Component({
  selector: 'estacion-app',
  standalone: true,
  template: `
<header><div class="brand"><span class="logo" aria-hidden="true">▥</span> Dactilia</div><span class="device"><i [class.on]="connected()"></i>{{connected() ? 'Lector conectado' : 'Lector sin confirmar'}}</span></header>
<main><p class="eyebrow">DIGITALPERSONA / U.ARE.U 4500</p><h1>Estación de huellas</h1>
<nav aria-label="Secciones"><button [class.selected]="mode()==='leer'" [disabled]="!available() || busy()" (click)="switchMode('leer')">Leer</button><button [class.selected]="mode()==='enrolar'" [disabled]="!available() || busy()" (click)="switchMode('enrolar')">Enrolar</button></nav>
@if(mode()==='enrolar'){
<div class="workflow"><h2>Enrolar una huella</h2>
@if(!activeName()){
<form (submit)="start($event)"><label for="nombre">Nombre de la persona</label>
<div class="entry"><input id="nombre" maxlength="120" autocomplete="off" [value]="name()" (input)="name.set($any($event.target).value)" placeholder="Nombre y apellido">
<button class="secondary" [disabled]="!name().trim() || busy()">Iniciar enrolamiento</button></div></form>
} @else {<p><strong>{{activeName()}}</strong> · {{accepted()}} de 3 capturas aceptadas</p>
<button class="link" (click)="switchMode('enrolar', true)">Cancelar enrolamiento</button>}
<p class="result" role="status">{{result()}}</p></div>
} @else {<div class="workflow"><h2>Identificación</h2><p class="result" role="status">{{result()}}</p></div>}
<div class="layout"><section><div class="section-title"><h2>{{sample() ? 'Lectura '+sample()!.sequence : 'Vista de captura'}}</h2><span>ESCALA DE GRISES</span></div>
<div class="viewer"><div class="frame">
@if (sample(); as s) {<img (load)="imageLoaded($event)" [src]="'data:image/png;base64,'+s.image" alt="Imagen de la huella capturada">}
@else {<div class="empty"><div class="scanmark">＋</div>Apoya un dedo en el lector</div>}
</div></div>
<div class="listening"><i></i>{{connected() ? "Escucha automática activa" : "Conectando con el lector…"}}</div></section><aside><div class="section-title"><h2>Datos de la imagen</h2></div>
<dl><div><dt>Formato</dt><dd>{{sample() ? 'PNG · 8 bits' : '—'}}</dd></div><div><dt>Dimensiones</dt><dd>{{sample() ? sample()!.width+' × '+sample()!.height+' px' : '—'}}</dd></div><div><dt>Tamaño</dt><dd>{{sample() ? sample()!.bytes+' bytes' : '—'}}</dd></div></dl>
<h3>Código SHA-256</h3><div class="hash">{{sample()?.hash || 'Disponible después de capturar'}}</div>
<button class="link" [disabled]="!sample()" (click)="copy()">Copiar código</button>
@if(mode()==='leer'){<hr><h3>Captura individual</h3><p>Guarda el PNG como BLOB en SQLite. El código identifica esta imagen exacta.</p>
<button class="secondary" [disabled]="!sample() || busy() || saved()" (click)="save()">{{saved() ? '✓ Guardada en SQLite' : 'Guardar en SQLite'}}</button>}
</aside></div><p class="status" role="status" aria-live="polite">{{status()}}</p></main>`
})
class Estacion {
  sample = signal<Capture|null>(null);
  connected = signal(false);
  busy = signal('');
  saved = signal(false);
  status = signal('Listo para comprobar el lector.');
  mode = signal('leer');
  available = signal(false);
  activeName = signal('');
  name = signal('');
  accepted = signal(0);
  result = signal('Conectando con el lector…');
  private version = 0;
  private alive = true;
  async switchMode(mode:string, reset=false) {
    if (!reset && mode===this.mode()) return;
    await this.configure(mode, '');
  }
  async start(event:Event) {
    event.preventDefault();
    const name=this.name().trim();
    if (name) await this.configure('enrolar',name);
  }
  private async configure(mode:string, name:string) {
    if (this.busy()) return;
    this.version++;
    this.busy.set('seccion');
    try {
      await this.bridge.seccion(mode,name);
      this.mode.set(mode); this.activeName.set(name); this.accepted.set(0);
      this.sample.set(null); this.saved.set(false); this.name.set('');
      this.result.set(name ? 'Apoya el mismo dedo tres veces.' : '');
    } catch(e) { this.result.set(String(e)); }
    finally {this.busy.set('');}
  }
  private get bridge() { return (window as any).pywebview?.api; }
  ngOnDestroy() { this.alive = false; }
  async ngOnInit() {
    while (this.alive) {
      try {
        if (this.bridge && this.busy()!=='seccion') {
          const version=this.version;
          const state = await this.bridge.estado(this.sample()?.sequence ?? 0);
          if (version!==this.version) continue;
          this.available.set(true);
          this.mode.set(state.modo); this.activeName.set(state.nombre);
          this.result.set(state.resultado); this.accepted.set(state.aceptadas);
          this.connected.set(state.connected);
          if (state.sample) { this.sample.set(state.sample); this.saved.set(false); }
          this.status.set(state.status);
        }
      } catch { this.status.set('Se interrumpió la comunicación con el lector.'); }
      await new Promise(done => setTimeout(done, 400));
    }
  }
  imageLoaded(event: Event) {
    const img = event.target as HTMLImageElement;
    const s = this.sample();
    if (s && document.querySelector('.hash')?.textContent?.trim() === s.hash) {
      this.bridge?.imagen_visible(s.hash, img.naturalWidth, img.naturalHeight);
    }
  }
  async save() {
    const s=this.sample(); if (!s || this.busy()) return;
    this.busy.set('guardar');
    try {await this.bridge.guardar(s.hash); this.saved.set(this.sample()?.hash === s.hash); this.status.set('Captura guardada en capturas.sqlite3.');}
    catch(e) {this.status.set(String(e));} finally {this.busy.set('');}
  }
  async copy() {
    const s=this.sample(); if (!s) return;
    try {await navigator.clipboard.writeText(s.hash); this.status.set('Código copiado.');}
    catch {this.status.set('Selecciona el código y pulsa Ctrl+C para copiarlo.');}
  }
}
bootstrapApplication(Estacion).catch(console.error);
