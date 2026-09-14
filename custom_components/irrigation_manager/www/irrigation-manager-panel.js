function t(t,e,i,s){var n,r=arguments.length,o=r<3?e:null===s?s=Object.getOwnPropertyDescriptor(e,i):s;if("object"==typeof Reflect&&"function"==typeof Reflect.decorate)o=Reflect.decorate(t,e,i,s);else for(var a=t.length-1;a>=0;a--)(n=t[a])&&(o=(r<3?n(o):r>3?n(e,i,o):n(e,i))||o);return r>3&&o&&Object.defineProperty(e,i,o),o}"function"==typeof SuppressedError&&SuppressedError;const e=globalThis,i=e.ShadowRoot&&(void 0===e.ShadyCSS||e.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,s=Symbol(),n=new WeakMap;let r=class{constructor(t,e,i){if(this._$cssResult$=!0,i!==s)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o;const e=this.t;if(i&&void 0===t){const i=void 0!==e&&1===e.length;i&&(t=n.get(e)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),i&&n.set(e,t))}return t}toString(){return this.cssText}};const o=i?t=>t:t=>t instanceof CSSStyleSheet?(t=>{let e="";for(const i of t.cssRules)e+=i.cssText;return(t=>new r("string"==typeof t?t:t+"",void 0,s))(e)})(t):t,{is:a,defineProperty:l,getOwnPropertyDescriptor:c,getOwnPropertyNames:d,getOwnPropertySymbols:h,getPrototypeOf:u}=Object,p=globalThis,_=p.trustedTypes,g=_?_.emptyScript:"",$=p.reactiveElementPolyfillSupport,m=(t,e)=>t,f={toAttribute(t,e){switch(e){case Boolean:t=t?g:null;break;case Object:case Array:t=null==t?t:JSON.stringify(t)}return t},fromAttribute(t,e){let i=t;switch(e){case Boolean:i=null!==t;break;case Number:i=null===t?null:Number(t);break;case Object:case Array:try{i=JSON.parse(t)}catch(t){i=null}}return i}},b=(t,e)=>!a(t,e),y={attribute:!0,type:String,converter:f,reflect:!1,useDefault:!1,hasChanged:b};Symbol.metadata??=Symbol("metadata"),p.litPropertyMetadata??=new WeakMap;let v=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=y){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){const i=Symbol(),s=this.getPropertyDescriptor(t,i,e);void 0!==s&&l(this.prototype,t,s)}}static getPropertyDescriptor(t,e,i){const{get:s,set:n}=c(this.prototype,t)??{get(){return this[e]},set(t){this[e]=t}};return{get:s,set(e){const r=s?.call(this);n?.call(this,e),this.requestUpdate(t,r,i)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??y}static _$Ei(){if(this.hasOwnProperty(m("elementProperties")))return;const t=u(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(m("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(m("properties"))){const t=this.properties,e=[...d(t),...h(t)];for(const i of e)this.createProperty(i,t[i])}const t=this[Symbol.metadata];if(null!==t){const e=litPropertyMetadata.get(t);if(void 0!==e)for(const[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(const[t,e]of this.elementProperties){const i=this._$Eu(t,e);void 0!==i&&this._$Eh.set(i,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const e=[];if(Array.isArray(t)){const i=new Set(t.flat(1/0).reverse());for(const t of i)e.unshift(o(t))}else void 0!==t&&e.push(o(t));return e}static _$Eu(t,e){const i=e.attribute;return!1===i?void 0:"string"==typeof i?i:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){const t=new Map,e=this.constructor.elementProperties;for(const i of e.keys())this.hasOwnProperty(i)&&(t.set(i,this[i]),delete this[i]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return((t,s)=>{if(i)t.adoptedStyleSheets=s.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const i of s){const s=document.createElement("style"),n=e.litNonce;void 0!==n&&s.setAttribute("nonce",n),s.textContent=i.cssText,t.appendChild(s)}})(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,i){this._$AK(t,i)}_$ET(t,e){const i=this.constructor.elementProperties.get(t),s=this.constructor._$Eu(t,i);if(void 0!==s&&!0===i.reflect){const n=(void 0!==i.converter?.toAttribute?i.converter:f).toAttribute(e,i.type);this._$Em=t,null==n?this.removeAttribute(s):this.setAttribute(s,n),this._$Em=null}}_$AK(t,e){const i=this.constructor,s=i._$Eh.get(t);if(void 0!==s&&this._$Em!==s){const t=i.getPropertyOptions(s),n="function"==typeof t.converter?{fromAttribute:t.converter}:void 0!==t.converter?.fromAttribute?t.converter:f;this._$Em=s;const r=n.fromAttribute(e,t.type);this[s]=r??this._$Ej?.get(s)??r,this._$Em=null}}requestUpdate(t,e,i){if(void 0!==t){const s=this.constructor,n=this[t];if(i??=s.getPropertyOptions(t),!((i.hasChanged??b)(n,e)||i.useDefault&&i.reflect&&n===this._$Ej?.get(t)&&!this.hasAttribute(s._$Eu(t,i))))return;this.C(t,e,i)}!1===this.isUpdatePending&&(this._$ES=this._$EP())}C(t,e,{useDefault:i,reflect:s,wrapped:n},r){i&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,r??e??this[t]),!0!==n||void 0!==r)||(this._$AL.has(t)||(this.hasUpdated||i||(e=void 0),this._$AL.set(t,e)),!0===s&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[t,e]of this._$Ep)this[t]=e;this._$Ep=void 0}const t=this.constructor.elementProperties;if(t.size>0)for(const[e,i]of t){const{wrapped:t}=i,s=this[e];!0!==t||this._$AL.has(e)||void 0===s||this.C(e,void 0,i,s)}}let t=!1;const e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(e){throw t=!1,this._$EM(),e}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(t){}firstUpdated(t){}};v.elementStyles=[],v.shadowRootOptions={mode:"open"},v[m("elementProperties")]=new Map,v[m("finalized")]=new Map,$?.({ReactiveElement:v}),(p.reactiveElementVersions??=[]).push("2.1.1");const x=globalThis,w=x.trustedTypes,A=w?w.createPolicy("lit-html",{createHTML:t=>t}):void 0,k="$lit$",S=`lit$${Math.random().toFixed(9).slice(2)}$`,E="?"+S,C=`<${E}>`,H=document,M=()=>H.createComment(""),z=t=>null===t||"object"!=typeof t&&"function"!=typeof t,P=Array.isArray,L="[ \t\n\f\r]",R=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,N=/-->/g,U=/>/g,O=RegExp(`>|${L}(?:([^\\s"'>=/]+)(${L}*=${L}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,"g"),T=/'/g,j=/"/g,D=/^(?:script|style|textarea|title)$/i,V=(t=>(e,...i)=>({_$litType$:t,strings:e,values:i}))(1),B=Symbol.for("lit-noChange"),I=Symbol.for("lit-nothing"),W=new WeakMap,q=H.createTreeWalker(H,129);function Z(t,e){if(!P(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==A?A.createHTML(e):e}const F=(t,e)=>{const i=t.length-1,s=[];let n,r=2===e?"<svg>":3===e?"<math>":"",o=R;for(let e=0;e<i;e++){const i=t[e];let a,l,c=-1,d=0;for(;d<i.length&&(o.lastIndex=d,l=o.exec(i),null!==l);)d=o.lastIndex,o===R?"!--"===l[1]?o=N:void 0!==l[1]?o=U:void 0!==l[2]?(D.test(l[2])&&(n=RegExp("</"+l[2],"g")),o=O):void 0!==l[3]&&(o=O):o===O?">"===l[0]?(o=n??R,c=-1):void 0===l[1]?c=-2:(c=o.lastIndex-l[2].length,a=l[1],o=void 0===l[3]?O:'"'===l[3]?j:T):o===j||o===T?o=O:o===N||o===U?o=R:(o=O,n=void 0);const h=o===O&&t[e+1].startsWith("/>")?" ":"";r+=o===R?i+C:c>=0?(s.push(a),i.slice(0,c)+k+i.slice(c)+S+h):i+S+(-2===c?e:h)}return[Z(t,r+(t[i]||"<?>")+(2===e?"</svg>":3===e?"</math>":"")),s]};class K{constructor({strings:t,_$litType$:e},i){let s;this.parts=[];let n=0,r=0;const o=t.length-1,a=this.parts,[l,c]=F(t,e);if(this.el=K.createElement(l,i),q.currentNode=this.el.content,2===e||3===e){const t=this.el.content.firstChild;t.replaceWith(...t.childNodes)}for(;null!==(s=q.nextNode())&&a.length<o;){if(1===s.nodeType){if(s.hasAttributes())for(const t of s.getAttributeNames())if(t.endsWith(k)){const e=c[r++],i=s.getAttribute(t).split(S),o=/([.?@])?(.*)/.exec(e);a.push({type:1,index:n,name:o[2],strings:i,ctor:"."===o[1]?Y:"?"===o[1]?tt:"@"===o[1]?et:X}),s.removeAttribute(t)}else t.startsWith(S)&&(a.push({type:6,index:n}),s.removeAttribute(t));if(D.test(s.tagName)){const t=s.textContent.split(S),e=t.length-1;if(e>0){s.textContent=w?w.emptyScript:"";for(let i=0;i<e;i++)s.append(t[i],M()),q.nextNode(),a.push({type:2,index:++n});s.append(t[e],M())}}}else if(8===s.nodeType)if(s.data===E)a.push({type:2,index:n});else{let t=-1;for(;-1!==(t=s.data.indexOf(S,t+1));)a.push({type:7,index:n}),t+=S.length-1}n++}}static createElement(t,e){const i=H.createElement("template");return i.innerHTML=t,i}}function G(t,e,i=t,s){if(e===B)return e;let n=void 0!==s?i._$Co?.[s]:i._$Cl;const r=z(e)?void 0:e._$litDirective$;return n?.constructor!==r&&(n?._$AO?.(!1),void 0===r?n=void 0:(n=new r(t),n._$AT(t,i,s)),void 0!==s?(i._$Co??=[])[s]=n:i._$Cl=n),void 0!==n&&(e=G(t,n._$AS(t,e.values),n,s)),e}let J=class{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:e},parts:i}=this._$AD,s=(t?.creationScope??H).importNode(e,!0);q.currentNode=s;let n=q.nextNode(),r=0,o=0,a=i[0];for(;void 0!==a;){if(r===a.index){let e;2===a.type?e=new Q(n,n.nextSibling,this,t):1===a.type?e=new a.ctor(n,a.name,a.strings,this,t):6===a.type&&(e=new it(n,this,t)),this._$AV.push(e),a=i[++o]}r!==a?.index&&(n=q.nextNode(),r++)}return q.currentNode=H,s}p(t){let e=0;for(const i of this._$AV)void 0!==i&&(void 0!==i.strings?(i._$AI(t,i,e),e+=i.strings.length-2):i._$AI(t[e])),e++}};class Q{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,i,s){this.type=2,this._$AH=I,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=i,this.options=s,this._$Cv=s?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode;const e=this._$AM;return void 0!==e&&11===t?.nodeType&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=G(this,t,e),z(t)?t===I||null==t||""===t?(this._$AH!==I&&this._$AR(),this._$AH=I):t!==this._$AH&&t!==B&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):(t=>P(t)||"function"==typeof t?.[Symbol.iterator])(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==I&&z(this._$AH)?this._$AA.nextSibling.data=t:this.T(H.createTextNode(t)),this._$AH=t}$(t){const{values:e,_$litType$:i}=t,s="number"==typeof i?this._$AC(t):(void 0===i.el&&(i.el=K.createElement(Z(i.h,i.h[0]),this.options)),i);if(this._$AH?._$AD===s)this._$AH.p(e);else{const t=new J(s,this),i=t.u(this.options);t.p(e),this.T(i),this._$AH=t}}_$AC(t){let e=W.get(t.strings);return void 0===e&&W.set(t.strings,e=new K(t)),e}k(t){P(this._$AH)||(this._$AH=[],this._$AR());const e=this._$AH;let i,s=0;for(const n of t)s===e.length?e.push(i=new Q(this.O(M()),this.O(M()),this,this.options)):i=e[s],i._$AI(n),s++;s<e.length&&(this._$AR(i&&i._$AB.nextSibling,s),e.length=s)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){const e=t.nextSibling;t.remove(),t=e}}setConnected(t){void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t))}}class X{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,i,s,n){this.type=1,this._$AH=I,this._$AN=void 0,this.element=t,this.name=e,this._$AM=s,this.options=n,i.length>2||""!==i[0]||""!==i[1]?(this._$AH=Array(i.length-1).fill(new String),this.strings=i):this._$AH=I}_$AI(t,e=this,i,s){const n=this.strings;let r=!1;if(void 0===n)t=G(this,t,e,0),r=!z(t)||t!==this._$AH&&t!==B,r&&(this._$AH=t);else{const s=t;let o,a;for(t=n[0],o=0;o<n.length-1;o++)a=G(this,s[i+o],e,o),a===B&&(a=this._$AH[o]),r||=!z(a)||a!==this._$AH[o],a===I?t=I:t!==I&&(t+=(a??"")+n[o+1]),this._$AH[o]=a}r&&!s&&this.j(t)}j(t){t===I?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}}class Y extends X{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===I?void 0:t}}class tt extends X{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==I)}}class et extends X{constructor(t,e,i,s,n){super(t,e,i,s,n),this.type=5}_$AI(t,e=this){if((t=G(this,t,e,0)??I)===B)return;const i=this._$AH,s=t===I&&i!==I||t.capture!==i.capture||t.once!==i.once||t.passive!==i.passive,n=t!==I&&(i===I||s);s&&this.element.removeEventListener(this.name,this,i),n&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}}class it{constructor(t,e,i){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=i}get _$AU(){return this._$AM._$AU}_$AI(t){G(this,t)}}const st={I:Q},nt=x.litHtmlPolyfillSupport;nt?.(K,Q),(x.litHtmlVersions??=[]).push("3.3.1");const rt=globalThis;let ot=class extends v{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=((t,e,i)=>{const s=i?.renderBefore??e;let n=s._$litPart$;if(void 0===n){const t=i?.renderBefore??null;s._$litPart$=n=new Q(e.insertBefore(M(),t),t,void 0,i??{})}return n._$AI(t),n})(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return B}};ot._$litElement$=!0,ot.finalized=!0,rt.litElementHydrateSupport?.({LitElement:ot});const at=rt.litElementPolyfillSupport;at?.({LitElement:ot}),(rt.litElementVersions??=[]).push("4.2.1");const lt={attribute:!0,type:String,converter:f,reflect:!1,hasChanged:b},ct=(t=lt,e,i)=>{const{kind:s,metadata:n}=i;let r=globalThis.litPropertyMetadata.get(n);if(void 0===r&&globalThis.litPropertyMetadata.set(n,r=new Map),"setter"===s&&((t=Object.create(t)).wrapped=!0),r.set(i.name,t),"accessor"===s){const{name:s}=i;return{set(i){const n=e.get.call(this);e.set.call(this,i),this.requestUpdate(s,n,t)},init(e){return void 0!==e&&this.C(s,void 0,t,e),e}}}if("setter"===s){const{name:s}=i;return function(i){const n=this[s];e.call(this,i),this.requestUpdate(s,n,t)}}throw Error("Unsupported decorator location: "+s)};function dt(t){return(e,i)=>"object"==typeof i?ct(t,e,i):((t,e,i)=>{const s=e.hasOwnProperty(i);return e.constructor.createProperty(i,t),s?Object.getOwnPropertyDescriptor(e,i):void 0})(t,e,i)}function ht(t){return dt({...t,state:!0,attribute:!1})}const ut=2;class pt{constructor(t){}get _$AU(){return this._$AM._$AU}_$AT(t,e,i){this._$Ct=t,this._$AM=e,this._$Ci=i}_$AS(t,e){return this.update(t,e)}update(t,e){return this.render(...e)}}const{I:_t}=st,gt=()=>document.createComment(""),$t=(t,e,i)=>{const s=t._$AA.parentNode,n=void 0===e?t._$AB:e._$AA;if(void 0===i){const e=s.insertBefore(gt(),n),r=s.insertBefore(gt(),n);i=new _t(e,r,t,t.options)}else{const e=i._$AB.nextSibling,r=i._$AM,o=r!==t;if(o){let e;i._$AQ?.(t),i._$AM=t,void 0!==i._$AP&&(e=t._$AU)!==r._$AU&&i._$AP(e)}if(e!==n||o){let t=i._$AA;for(;t!==e;){const e=t.nextSibling;s.insertBefore(t,n),t=e}}}return i},mt=(t,e,i=t)=>(t._$AI(e,i),t),ft={},bt=t=>{t._$AR(),t._$AA.remove()},yt=(t,e,i)=>{const s=new Map;for(let n=e;n<=i;n++)s.set(t[n],n);return s},vt=(t=>(...e)=>({_$litDirective$:t,values:e}))(class extends pt{constructor(t){if(super(t),t.type!==ut)throw Error("repeat() can only be used in text expressions")}dt(t,e,i){let s;void 0===i?i=e:void 0!==e&&(s=e);const n=[],r=[];let o=0;for(const e of t)n[o]=s?s(e,o):o,r[o]=i(e,o),o++;return{values:r,keys:n}}render(t,e,i){return this.dt(t,e,i).values}update(t,[e,i,s]){const n=(t=>t._$AH)(t),{values:r,keys:o}=this.dt(e,i,s);if(!Array.isArray(n))return this.ut=o,r;const a=this.ut??=[],l=[];let c,d,h=0,u=n.length-1,p=0,_=r.length-1;for(;h<=u&&p<=_;)if(null===n[h])h++;else if(null===n[u])u--;else if(a[h]===o[p])l[p]=mt(n[h],r[p]),h++,p++;else if(a[u]===o[_])l[_]=mt(n[u],r[_]),u--,_--;else if(a[h]===o[_])l[_]=mt(n[h],r[_]),$t(t,l[_+1],n[h]),h++,_--;else if(a[u]===o[p])l[p]=mt(n[u],r[p]),$t(t,n[h],n[u]),u--,p++;else if(void 0===c&&(c=yt(o,p,_),d=yt(a,h,u)),c.has(a[h]))if(c.has(a[u])){const e=d.get(o[p]),i=void 0!==e?n[e]:null;if(null===i){const e=$t(t,n[h]);mt(e,r[p]),l[p]=e}else l[p]=mt(i,r[p]),$t(t,n[h],i),n[e]=null;p++}else bt(n[u]),u--;else bt(n[h]),h++;for(;p<=_;){const e=$t(t,l[_+1]);mt(e,r[p]),l[p++]=e}for(;h<=u;){const t=n[h++];null!==t&&bt(t)}return this.ut=o,((t,e=ft)=>{t._$AH=e})(t,l),B}}),xt=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],wt={idle:{label:"Idle",tone:"muted"},running:{label:"Running",tone:"info"},disabled:{label:"Disabled",tone:"muted"},paused:{label:"Paused",tone:"muted"},skipped_rain:{label:"Skipped: rain",tone:"warn"},skipped_forecast:{label:"Skipped: forecast",tone:"warn"},skipped_temperature:{label:"Skipped: temperature",tone:"warn"},skipped_wind:{label:"Skipped: wind",tone:"warn"},skipped_occupancy:{label:"Skipped: occupied",tone:"warn"},skipped_moisture:{label:"Skipped: soil moisture",tone:"warn"},skipped_rain_delay:{label:"Skipped: rain delay",tone:"warn"},skipped_manual:{label:"Skipped: manual",tone:"warn"},skipped_busy:{label:"Skipped: still running",tone:"warn"},stopped_rain:{label:"Stopped: rain started",tone:"warn"},stopped_occupancy:{label:"Stopped: occupied",tone:"warn"},interrupted:{label:"Interrupted",tone:"error"},error:{label:"Error",tone:"error"}},At=t=>wt[t]?.label??t,kt=(t,e)=>e?t.states[e]?.attributes.friendly_name??e:"",St=(t,e)=>e.map(e=>kt(t,e)).join(", "),Et=(t,e)=>{const i=t.states[e??""]?.attributes.unit_of_measurement;return i?` ${i}`:""},Ct=t=>t.locale?.language??t.language??"en",Ht=t=>{const e={};return"local"!==t.locale?.time_zone&&t.config?.time_zone&&(e.timeZone=t.config.time_zone),"12"===t.locale?.time_format?e.hour12=!0:"24"===t.locale?.time_format&&(e.hour12=!1),e},Mt=(t,e,i=2)=>Number(e).toLocaleString(Ct(t),{maximumFractionDigits:i}),zt=(t,e)=>new Date(e).toLocaleString(Ct(t),{...Ht(t),weekday:"short",month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}),Pt=(t,e)=>new Date(e).toLocaleTimeString(Ct(t),{...Ht(t),hour:"numeric",minute:"2-digit"}),Lt=(t,e)=>`${t} ${e}${1===t?"":"s"}`,Rt=t=>{const e=Math.floor(t/1440),i=Math.floor(t%1440/60),s=t%60;return e>0?i>0?`${e} d ${i} h`:`${e} d`:i>0?s>0?`${i} h ${s} min`:`${i} h`:`${s} min`},Nt=(t,e)=>{const i=Math.round((new Date(t).getTime()-e)/6e4);return 0===i?"now":i>0?`in ${Rt(i)}`:`${Rt(-i)} ago`},Ut=(t,e)=>{if("interval"===e.frequency){const i=e.interval_days??1,s=1===i?"Every day":`Every ${i} days`;return e.anchor?`${s} from ${((t,e)=>{const[i,s,n]=e.split("-").map(Number);return i&&s&&n?new Date(i,s-1,n).toLocaleDateString(Ct(t),{weekday:"short",month:"short",day:"numeric",year:"numeric"}):e})(t,e.anchor)}`:s}const i=[...e.weekdays??[]].sort((t,e)=>t-e);return 7===i.length?"Every day":i.length?i.map(t=>xt[t]??String(t)).join(", "):"No days"},Ot=(t,e)=>{if("time"===e.start_mode)return e.start_time?`Starts at ${((t,e)=>{const[i,s]=e.split(":").map(Number);if(Number.isNaN(i)||Number.isNaN(s))return e;const{hour12:n}=Ht(t);return new Date(2e3,0,1,i,s).toLocaleTimeString(Ct(t),{hour:"numeric",minute:"2-digit",...void 0===n?{}:{hour12:n}})})(t,e.start_time)}`:"Fixed time";const i="sunset"===e.start_mode?"sunset":"sunrise",s=e.sun_offset_minutes??0;return 0===s?`Finishes at ${i}`:s>0?`Finishes ${Rt(s)} before ${i}`:`Finishes ${Rt(-s)} after ${i}`},Tt=t=>t.weather_entities?.length?t.weather_entities:t.weather_entity?[t.weather_entity]:[],jt=t=>null!=t,Dt=(t,e)=>({text:`${t}: no data${e.reason?` (${e.reason})`:""}`,tone:"muted"}),Vt=(t,e)=>{const i=e??{},s=[];return i.manual&&s.push({text:"Started manually"}),s.push(...((t,e)=>{if(!e)return[];if(!jt(e.total))return[Dt("Rain",e)];const i=e.unit?` ${e.unit}`:"",s=`${Mt(t,e.threshold??0)}${i}`,n="since_last_watering"===e.window&&e.window_start?`since ${zt(t,e.window_start)}`:`in the last ${Lt(e.hours??0,"hour")}`,r=e.stations,o=[];if(r&&"quorum"===e.aggregate){const t=(e.stations_over??0)>=(e.quorum??1);o.push({text:`Rain ${n}: ${e.stations_over??0} of ${e.stations_reporting??0} stations ≥ ${s} (need ${e.quorum??1})`,tone:t?"warn":void 0})}else{const a=r?"median"===e.aggregate?"Median rain":"Most rain":"Rain",l=jt(e.threshold)&&e.total>=e.threshold;o.push({text:`${a} ${Mt(t,e.total)}${i} ${n} ${l?"≥":"<"} ${s}`,tone:l?"warn":void 0})}return r&&o.push({text:Object.entries(r).map(([e,s])=>`${kt(t,e)}: ${jt(s.total)?`${Mt(t,s.total)}${i}`:"no data"}`).join(" · "),tone:"muted"}),o})(t,i.rain),...((t,e)=>{if(!e)return[];const i=jt(e.max_probability),s=jt(e.amount);if(!i&&!s)return[Dt("Forecast",e)];const n=e.mode??"probability",r=[];if(i&&"amount"!==n){const i=jt(e.threshold)&&e.max_probability>=e.threshold,s=e.at?` at ${zt(t,e.at)}`:"";r.push({text:`Forecast ${e.max_probability}% rain chance${s} ${i?"≥":"<"} ${e.threshold}%`+(e.forecast_type?` (${String(e.forecast_type).replace("_"," ")})`:""),tone:i?"warn":void 0})}if(s&&"probability"!==n){const i=e.amount_unit?` ${e.amount_unit}`:"",s=jt(e.amount_threshold)&&e.amount>=e.amount_threshold;r.push({text:`Forecast rain ${Mt(t,e.amount)}${i} in the next ${Lt(e.hours??0,"hour")} ${s?"≥":"<"} ${Mt(t,e.amount_threshold??0)}${i}`,tone:s?"warn":void 0})}if(e.entities){const t=(e.entities_triggering??0)>=(e.quorum??1);r.push({text:`${e.entities_triggering??0} of ${e.entities_available??0} forecasts reached the limit (need ${e.quorum??1})`,tone:t?"warn":"muted"})}return r})(t,i.forecast),...((t,e)=>{if(!e)return[];const i=jt(e.current),s=jt(e.forecast_low);if(!i&&!s)return[Dt("Temperature",e)];const n=e.unit??"",r=[];i&&r.push(`${Mt(t,e.current,1)}${n} now`),s&&r.push(`forecast low ${Mt(t,e.forecast_low,1)}${n}`);const o=[];jt(e.min)&&o.push(`min ${Mt(t,e.min,1)}${n}`),jt(e.max)&&o.push(`max ${Mt(t,e.max,1)}${n}`);const a=[{text:`Temperature ${r.join(", ")}`+(o.length?` (${o.join(", ")})`:"")+({freeze:" — at or below the minimum",freeze_forecast:" — forecast low at or below the minimum",heat:" — at or above the maximum"}[e.trigger]??""),tone:e.trigger?"warn":void 0}];return e.sensor_reason&&a.push({text:`Temperature sensor: ${e.sensor_reason}`,tone:"muted"}),a})(t,i.temperature),...((t,e)=>{if(!e)return[];if(!jt(e.average))return[Dt("Wind",e)];const i=e.unit?` ${e.unit}`:"",s=jt(e.max)&&e.average>=e.max;return[{text:`Wind ${Mt(t,e.average,1)}${i} average over ${e.minutes??0} min ${s?"≥":"<"} ${Mt(t,e.max??0,1)}${i}`,tone:s?"warn":void 0}]})(t,i.wind),...((t,e)=>{if(!e)return[];if(e.reason)return[Dt("Occupancy",e)];const i=e.occupied??[];return i.length?[{text:`Occupied: ${St(t,i)}`,tone:"warn"}]:[{text:"Not occupied",tone:"muted"}]})(t,i.occupancy),...((t,e)=>{if(!e)return[];const i=[];if(jt(e.lowest)){const s=jt(e.threshold)&&e.lowest<e.threshold;i.push({text:`Lowest moisture ${Mt(t,e.lowest,1)}% (${kt(t,e.lowest_entity)}) ${s?"<":"≥"} ${Mt(t,e.threshold??0,1)}%`})}else i.push(Dt("Soil moisture",e));const s=e.unavailable_entities??[];return s.length&&i.push({text:`No reading from ${St(t,s)}`,tone:"muted"}),i})(t,i.moisture)),i.occupancy_delay_until&&s.push({text:`Waiting for occupancy to clear, up to ${zt(t,i.occupancy_delay_until)}`,tone:"info"}),i.skipped_busy_at&&s.push({text:`Skipped a start at ${zt(t,i.skipped_busy_at)} because a run was still going`,tone:"warn"}),i.error&&s.push({text:String(i.error),tone:"error"}),s},Bt="M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z",It="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z",Wt="M8,5.14V19.14L19,12.14L8,5.14Z",qt="M18,18H6V6H18V18Z",Zt="M16,18H18V6H16M6,18L14.5,12L6,6V18Z",Ft="M12.5,8C9.85,8 7.45,9 5.6,10.6L2,7V16H11L7.38,12.38C8.77,11.22 10.54,10.5 12.5,10.5C16.04,10.5 19.05,12.81 20.1,16L22.47,15.22C21.08,11.03 17.15,8 12.5,8Z",Kt="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z",Gt="M12,20A6,6 0 0,1 6,14C6,10 12,3.25 12,3.25C12,3.25 18,10 18,14A6,6 0 0,1 12,20Z",Jt="M14,19H18V5H14M6,19H10V5H6V19Z",Qt="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z",Xt="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z",Yt="M13,14H11V10H13M13,18H11V16H13M1,21H23L12,2L1,21Z",te="M12,2A2,2 0 0,1 14,4C14,4.74 13.6,5.39 13,5.73V7H14A7,7 0 0,1 21,14H22A1,1 0 0,1 23,15V18A1,1 0 0,1 22,19H21V20A2,2 0 0,1 19,22H5A2,2 0 0,1 3,20V19H2A1,1 0 0,1 1,18V15A1,1 0 0,1 2,14H3A7,7 0 0,1 10,7H11V5.73C10.4,5.39 10,4.74 10,4A2,2 0 0,1 12,2M7.5,13A2.5,2.5 0 0,0 5,15.5A2.5,2.5 0 0,0 7.5,18A2.5,2.5 0 0,0 10,15.5A2.5,2.5 0 0,0 7.5,13M16.5,13A2.5,2.5 0 0,0 14,15.5A2.5,2.5 0 0,0 16.5,18A2.5,2.5 0 0,0 19,15.5A2.5,2.5 0 0,0 16.5,13Z",ee=t=>V`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d=${t}></path></svg>`,ie=((t,...e)=>{const i=1===t.length?t[0]:e.reduce((e,i,s)=>e+(t=>{if(!0===t._$cssResult$)return t.cssText;if("number"==typeof t)return t;throw Error("Value passed to 'css' function must be a 'css' function result: "+t+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+t[s+1],t[0]);return new r(i,t,s)})`
  :host {
    display: block;
    min-height: 100vh;
    background: var(--primary-background-color, #fafafa);
    color: var(--primary-text-color, #212121);
    font-family: var(--ha-font-family-body, var(--paper-font-body1_-_font-family, Roboto, sans-serif));
    -webkit-font-smoothing: antialiased;
  }

  .toolbar {
    position: sticky;
    top: 0;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: 8px;
    box-sizing: border-box;
    height: var(--header-height, 56px);
    padding: 0 12px 0 16px;
    background: var(--app-header-background-color, var(--primary-color, #03a9f4));
    color: var(--app-header-text-color, var(--text-primary-color, #fff));
    border-bottom: var(--app-header-border-bottom, none);
  }

  .title {
    flex: 1;
    min-width: 0;
    font-size: 20px;
    font-weight: 400;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  button {
    font: inherit;
  }

  .icon-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    margin-left: -8px;
    border: none;
    border-radius: 50%;
    background: transparent;
    color: inherit;
    cursor: pointer;
  }

  .icon-button .icon {
    width: 24px;
    height: 24px;
  }

  .toolbar-button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border: 1px solid currentColor;
    border-radius: 18px;
    background: transparent;
    color: inherit;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
  }

  .icon-button:hover,
  .toolbar-button:hover {
    background: rgba(127, 127, 127, 0.18);
  }

  .content {
    box-sizing: border-box;
    max-width: 1400px;
    margin: 0 auto;
    padding: 16px;
  }

  :host([narrow]) .content {
    padding: 8px;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 16px;
    align-items: start;
  }

  :host([narrow]) .grid {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .card {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--ha-card-background, var(--card-background-color, #fff));
    border-radius: var(--ha-card-border-radius, 12px);
    border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
    box-shadow: var(--ha-card-box-shadow, none);
  }

  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 16px 16px 8px;
  }

  .heading {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 500;
    overflow-wrap: anywhere;
  }

  .is-disabled h2 {
    color: var(--secondary-text-color, #727272);
  }

  .badge,
  .chip {
    display: inline-block;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 500;
    line-height: 18px;
    white-space: nowrap;
  }

  .badge {
    padding: 1px 8px;
    color: var(--secondary-text-color, #727272);
    background: rgba(127, 127, 127, 0.15);
  }

  .badge.ok {
    color: var(--success-color, #43a047);
    background: rgba(var(--rgb-success-color, 67, 160, 71), 0.15);
  }

  .badge.info {
    color: var(--info-color, #039be5);
    background: rgba(var(--rgb-info-color, 3, 155, 229), 0.15);
  }

  .badge.warn {
    color: var(--warning-color, #ffa600);
    background: rgba(var(--rgb-warning-color, 255, 166, 0), 0.18);
  }

  .badge.error {
    color: var(--error-color, #db4437);
    background: rgba(var(--rgb-error-color, 219, 68, 55), 0.15);
  }

  .chip {
    margin-left: 4px;
    padding: 0 6px;
    border: 1px solid var(--divider-color, #e0e0e0);
    color: var(--secondary-text-color, #727272);
  }

  .chip.warn {
    border-color: var(--warning-color, #ffa600);
    color: var(--warning-color, #ffa600);
  }

  .switch {
    position: relative;
    display: inline-flex;
    flex: none;
    cursor: pointer;
  }

  .switch input {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: 0;
    opacity: 0;
  }

  .track {
    position: relative;
    width: 36px;
    height: 20px;
    border-radius: 10px;
    background: var(--switch-unchecked-track-color, rgba(127, 127, 127, 0.45));
    transition: background 0.2s;
  }

  .thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--switch-unchecked-button-color, #fafafa);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
    transition: transform 0.2s;
  }

  .switch input:checked + .track {
    background: var(--switch-checked-track-color, var(--primary-color, #03a9f4));
  }

  .switch input:checked + .track .thumb {
    transform: translateX(16px);
    background: var(--switch-checked-button-color, #fff);
  }

  .switch input:disabled + .track {
    opacity: 0.5;
  }

  .switch input:focus-visible + .track,
  button:focus-visible {
    outline: 2px solid var(--primary-color, #03a9f4);
    outline-offset: 2px;
  }

  .running-block {
    margin: 0 16px 8px;
    padding: 10px 12px;
    border-radius: 8px;
    background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.12);
  }

  .running-title {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
    color: var(--primary-color, #03a9f4);
    font-weight: 500;
  }

  .running-zone {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    font-size: 14px;
  }

  .countdown {
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .rows {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    column-gap: 16px;
    row-gap: 10px;
    margin: 0;
    padding: 4px 16px 12px;
    font-size: 14px;
    line-height: 20px;
  }

  dt {
    color: var(--secondary-text-color, #727272);
  }

  dd {
    margin: 0;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .muted {
    color: var(--secondary-text-color, #727272);
  }

  .detail.warn {
    color: var(--warning-color, #ffa600);
  }

  .detail.error,
  .zone-list li.error {
    color: var(--error-color, #db4437);
  }

  .detail.muted {
    color: var(--secondary-text-color, #727272);
  }

  .zone-list {
    display: grid;
    gap: 2px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .zone-list li {
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }

  .zone-list .zone-error {
    display: block;
    font-size: 13px;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-top: auto;
    padding: 12px 16px 16px;
    border-top: 1px solid var(--divider-color, #e0e0e0);
  }

  .spacer {
    flex: 1;
  }

  .action {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border: none;
    border-radius: 18px;
    background: transparent;
    color: var(--primary-color, #03a9f4);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
  }

  .action:hover {
    background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.1);
  }

  .action.filled {
    background: var(--primary-color, #03a9f4);
    color: var(--text-primary-color, #fff);
  }

  .action.danger {
    background: var(--error-color, #db4437);
    color: #fff;
  }

  .action.filled:hover,
  .action.danger:hover {
    filter: brightness(1.08);
  }

  .action:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .icon {
    width: 18px;
    height: 18px;
    flex: none;
    fill: currentColor;
  }

  .banner {
    margin-bottom: 16px;
    padding: 10px 12px;
    border-radius: 8px;
    font-size: 14px;
  }

  .banner.error {
    color: var(--error-color, #db4437);
    background: rgba(var(--rgb-error-color, 219, 68, 55), 0.12);
  }

  .card-banner {
    margin: 0 16px 12px;
  }

  .empty {
    padding: 48px 16px;
    text-align: center;
    color: var(--secondary-text-color, #727272);
  }

  .empty h2 {
    margin: 8px 0;
    color: var(--primary-text-color, #212121);
  }

  .empty p {
    max-width: 420px;
    margin: 0 auto 16px;
  }

  .empty-icon .icon {
    width: 48px;
    height: 48px;
    color: var(--primary-color, #03a9f4);
  }

  .banner.warn {
    color: var(--warning-color, #ffa600);
    background: rgba(var(--rgb-warning-color, 255, 166, 0), 0.14);
  }

  .banner .icon {
    margin-right: 6px;
    vertical-align: -3px;
  }

  .global-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 8px;
    margin-bottom: 12px;
  }

  .inline-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 4px;
  }

  .mini {
    padding: 2px 10px;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 12px;
    background: transparent;
    color: var(--primary-color, #03a9f4);
    font-size: 13px;
    line-height: 18px;
    cursor: pointer;
  }

  .mini:hover {
    background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.1);
  }

  .mini:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .zone-controls {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
  }

  .history-list {
    display: grid;
    gap: 2px;
    margin: 0 0 4px;
    padding: 0;
    list-style: none;
  }

  .history-list li {
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }

  .history-list li.error {
    color: var(--error-color, #db4437);
  }

  .detail.ok {
    color: var(--success-color, #43a047);
  }

  .detail.info {
    color: var(--info-color, #039be5);
  }

  .check-block {
    margin: 0 16px 12px;
    padding: 10px 12px;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 8px;
    font-size: 14px;
    line-height: 20px;
  }

  .check-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 4px;
    font-weight: 500;
  }

  .icon-button.small {
    width: 28px;
    height: 28px;
    margin: -4px -6px -4px 0;
    color: var(--secondary-text-color, #727272);
  }

  .icon-button.small .icon {
    width: 18px;
    height: 18px;
  }

  .dialog-backdrop {
    position: fixed;
    inset: 0;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    background: rgba(0, 0, 0, 0.45);
  }

  .dialog {
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    width: min(640px, 100%);
    max-height: calc(100vh - 32px);
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color, #212121);
    border-radius: var(--ha-dialog-border-radius, 16px);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  }

  .dialog h2 {
    padding: 20px 24px 8px;
  }

  .dialog-text {
    padding: 0 24px;
    overflow: auto;
    white-space: pre-wrap;
    font-size: 14px;
    line-height: 21px;
  }

  .dialog-actions {
    display: flex;
    justify-content: flex-end;
    padding: 16px 24px 20px;
  }

  @media (max-width: 450px) {
    .rows {
      grid-template-columns: minmax(0, 1fr);
      row-gap: 2px;
    }

    dt:not(:first-child) {
      margin-top: 8px;
    }

    .toolbar-button span {
      display: none;
    }
  }
`,se="irrigation_manager",ne=[24,48,72],re=t=>String(t&&"object"==typeof t&&"message"in t?t.message:t),oe=(t,e)=>{const{[e]:i,...s}=t;return s},ae=t=>{history.pushState(null,"",t),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}}))};let le=class extends ot{constructor(){super(...arguments),this.narrow=!1,this._pending={},this._actionErrors={},this._evaluations={},this._histories={},this._now=Date.now(),this._subscribeFailedAt=0,this._handleReconnect=()=>{if(!this._unsubscribe)return this._subscribeFailedAt=0,void this._subscribe();this._refresh()},this._closeDialog=()=>{this._dialog=void 0},this._handleKeydown=t=>{"Escape"===t.key&&this._dialog&&(this._dialog=void 0)}}connectedCallback(){super.connectedCallback(),this._subscribe(),this._timer=window.setInterval(()=>this._tick(),1e3),window.addEventListener("keydown",this._handleKeydown)}disconnectedCallback(){super.disconnectedCallback(),window.clearInterval(this._timer),this._timer=void 0,window.removeEventListener("keydown",this._handleKeydown),this._unsubscribeAll()}shouldUpdate(t){if(this._subscribe(),1!==t.size||!t.has("hass"))return!0;const e=t.get("hass"),i=this.hass;return!(e&&i&&this._schedules)||(e.locale!==i.locale||e.language!==i.language||e.config!==i.config||e.dockedSidebar!==i.dockedSidebar||this._watchedEntities().some(t=>e.states[t]!==i.states[t]))}render(){const t=this.hass,e=this.narrow||"always_hidden"===t?.dockedSidebar;return V`
      <div class="toolbar">
        ${e?V`<button class="icon-button" aria-label="Show sidebar" @click=${this._toggleMenu}>
              ${ee(Bt)}
            </button>`:I}
        <div class="title">Irrigation</div>
        <button class="toolbar-button" @click=${this._addSchedule}>
          ${ee(It)}<span>Add schedule</span>
        </button>
      </div>
      <main class="content">
        ${this._loadError?V`<div class="banner error" role="alert">${this._loadError}</div>`:I}
        ${this._renderGlobal()}
        ${this._renderBody(t)}
      </main>
      ${this._renderDialog()}
    `}_renderGlobal(){const t=this._schedules??[];if(!t.length)return I;const e=t.filter(t=>t.paused).length,i=t.some(t=>t.running),s=void 0!==this._globalPending;return V`
      ${e?V`<div class="banner warn" role="status">
            ${ee(Jt)}${e===t.length?"All schedules are paused. Scheduled runs do nothing until you resume.":`${e} of ${t.length} schedules are paused.`}
          </div>`:I}
      ${this._globalError?V`<div class="banner error" role="alert">${this._globalError}</div>`:I}
      <div class="global-actions">
        ${e<t.length?V`<button
              class="action"
              ?disabled=${s}
              @click=${()=>this._globalAction("pause_all")}
            >
              ${ee(Jt)}Pause all
            </button>`:I}
        ${e?V`<button
              class="action"
              ?disabled=${s}
              @click=${()=>this._globalAction("resume_all")}
            >
              ${ee(Wt)}Resume all
            </button>`:I}
        ${i?V`<button
              class="action danger"
              ?disabled=${s}
              @click=${()=>this._globalAction("stop_all")}
            >
              ${ee(qt)}Stop all
            </button>`:I}
      </div>
    `}_renderBody(t){return t&&void 0!==this._schedules?0===this._schedules.length?V`
        <div class="empty">
          <div class="empty-icon">${ee(Gt)}</div>
          <h2>No schedules yet</h2>
          <p>
            Add a schedule to choose valves or switches, set when they water, and pick
            rain, forecast, temperature, wind, occupancy or soil moisture conditions.
          </p>
          <button class="action filled" @click=${this._addSchedule}>
            ${ee(It)}Add schedule
          </button>
        </div>
      `:V`
      <div class="grid">
        ${vt(this._schedules,t=>t.entry_id,e=>this._renderSchedule(t,e))}
      </div>
    `:this._loadError?I:V`<div class="empty">Loading schedules…</div>`}_renderSchedule(t,e){const i=e.config??{},s=e.entry_id,n=this._pending[s],r=void 0!==n,o=this._actionErrors[s],a=((t,e)=>{const i=e.skip_conditions??[],s=[];if(i.includes("rain")){const i=(t=>t.rain_sensors?.length?t.rain_sensors:t.rain_sensor?[t.rain_sensor]:[])(e),n=Et(t,i[0]),r="since_last_watering"===e.rain_window?`since the last watering (at most ${Lt(e.rain_max_hours??168,"hour")})`:`in the last ${Lt(e.rain_hours??24,"hour")}`;let o;o=i.length<=1?kt(t,i[0]):"median"===e.rain_aggregate?`median of ${i.length} stations`:"quorum"===e.rain_aggregate?`at least ${e.rain_quorum??2} of ${i.length} stations`:`any of ${i.length} stations`,s.push(`Skip if ≥ ${Mt(t,e.rain_threshold??0)}${n} of rain ${r} (${o})`);const a=e.rain_delay_auto_hours??0;a>0?s.push(`After a rain skip, delay watering ${Lt(a,"hour")}`+(e.rain_delay_mirror?" (also on B-Hyve devices)":"")):e.rain_delay_mirror&&s.push("Rain delays are also set on B-Hyve devices"),e.rain_stop_during_run&&s.push(`Stop a run when ${Mt(t,e.rain_stop_amount??.05)}${n} of new rain falls`)}if(i.includes("forecast")){const i=Tt(e),n=`the rain chance is ≥ ${e.forecast_probability??0}%`,r=`the forecast rain is ≥ ${Mt(t,e.forecast_amount??0)}`,o=e.forecast_mode??"probability",a="amount"===o?r:"either"===o?`${n} or ${r}`:"both"===o?`${n} and ${r}`:n,l=Math.min(e.forecast_quorum??1,Math.max(i.length,1)),c=i.length<=1?kt(t,i[0]):l<=1?`any of ${i.length} forecasts`:`${l} of ${i.length} forecasts`;s.push(`Skip if ${a} in the next ${Lt(e.forecast_hours??12,"hour")} (${c})`)}if(i.includes("temperature")){const i=t.states[e.temperature_sensor??""]?.attributes.unit_of_measurement??"°",n=e.temperature_forecast_hours??12,r=[];if(jt(e.temperature_min)){const s=n>0&&Tt(e).length?` (or the forecast low in the next ${Lt(n,"hour")})`:"";r.push(`at or below ${Mt(t,e.temperature_min,1)}${i}${s}`)}if(jt(e.temperature_max)&&r.push(`at or above ${Mt(t,e.temperature_max,1)}${i}`),r.length){const i=e.temperature_sensor?` (${kt(t,e.temperature_sensor)})`:"";s.push(`Skip if the temperature is ${r.join(" or ")}${i}`)}(e.stale_hours??0)>0&&s.push(`Ignore a temperature reading older than ${Lt(e.stale_hours??0,"hour")}`)}if(i.includes("wind")&&s.push(`Skip if the average wind over ${e.wind_minutes??30} min is ≥ ${Mt(t,e.wind_max??0,1)}${Et(t,e.wind_sensor)} (${kt(t,e.wind_sensor)})`),i.includes("occupancy")){const i=St(t,e.occupancy_entities??[])||"an occupancy entity";s.push("skip"===e.occupancy_action?`Skip while ${i} is on`:`Wait up to ${e.occupancy_max_delay_minutes??60} min while ${i} is on, then skip`),e.occupancy_stop_during_run&&s.push("Stop a run when an occupancy entity turns on")}if(i.includes("moisture")){const i=e.moisture_sensors??[],n=1===i.length?kt(t,i[0]):`any of ${i.length} sensors`,r=Mt(t,e.moisture_threshold??0,1);if("trigger"===e.moisture_mode)s.push(`Also waters on other days when ${n} reads below ${r}%`);else{const t="skip"===e.moisture_unavailable?"skip":"water anyway";s.push(`Only waters when ${n} reads below ${r}% (no readings: ${t})`)}}return s})(t,i),l=((t,e)=>Vt(t,e.last_details))(t,e),c=e.unclosed_zones??[],d=this._evaluations[s];return V`
      <section class="card ${e.enabled?"":"is-disabled"}">
        <header class="card-header">
          <div class="heading">
            <h2>${e.name}</h2>
            <span class="badge ${h=e.status,wt[h]?.tone??"muted"}">${At(e.status)}</span>
            ${e.paused&&"paused"!==e.status?V`<span class="chip warn">paused</span>`:I}
          </div>
          <label class="switch" title=${e.enabled?"Turn schedule off":"Turn schedule on"}>
            <input
              type="checkbox"
              role="switch"
              aria-label="Schedule on"
              .checked=${e.enabled}
              ?disabled=${r}
              @change=${t=>this._toggleEnabled(e,t)}
            />
            <span class="track"><span class="thumb"></span></span>
          </label>
        </header>

        ${c.length?V`<div class="banner error card-banner" role="alert">
              ${ee(Yt)}Could not close
              ${c.map(e=>kt(t,e)).join(", ")}. Closing is being
              retried — check the valve.
            </div>`:I}

        ${e.running?this._renderRunning(t,e):I}

        <dl class="rows">
          <dt>Next run</dt>
          <dd>${this._renderNextRun(t,e)}</dd>

          <dt>Rain delay</dt>
          <dd>${this._renderRainDelay(t,e,r)}</dd>

          <dt>Schedule</dt>
          <dd>
            <div>${Ut(t,i)}</div>
            <div class="muted">${Ot(t,i)}</div>
          </dd>

          <dt>Zones</dt>
          <dd>${this._renderZones(t,e,r)}</dd>

          <dt>Conditions</dt>
          <dd>
            ${a.length?a.map(t=>V`<div>${t}</div>`):V`<span class="muted">None</span>`}
          </dd>

          <dt>Last run</dt>
          <dd>${this._renderLastRun(t,e)}</dd>

          ${e.last_status_at?V`
                <dt>Last status</dt>
                <dd>
                  <div>
                    ${At(e.status)}
                    <span class="muted">· ${zt(t,e.last_status_at)}</span>
                  </div>
                  ${l.map(t=>V`<div class="detail ${t.tone??""}">${t.text}</div>`)}
                </dd>
              `:I}

          <dt>History</dt>
          <dd>${this._renderHistory(t,e,r)}</dd>
        </dl>

        ${d?this._renderEvaluation(t,e,d):I}

        ${o?V`<div class="banner error card-banner" role="alert">${o}</div>`:I}

        <footer class="actions">
          ${e.running?V`<button
                class="action danger"
                ?disabled=${r}
                @click=${()=>this._action(e,"stop")}
              >
                ${ee(qt)}Stop
              </button>`:V`<button
                class="action filled"
                ?disabled=${r}
                @click=${()=>this._action(e,"run_now")}
              >
                ${ee(Wt)}Run now
              </button>`}
          <button
            class="action"
            ?disabled=${r}
            @click=${()=>this._action(e,"skip_next",{skip:!e.skip_next})}
          >
            ${e.skip_next?V`${ee(Ft)}Cancel skip`:V`${ee(Zt)}Skip next`}
          </button>
          <button class="action" ?disabled=${r} @click=${()=>this._evaluate(e)}>
            ${ee(Qt)}${"evaluate"===n?"Checking…":"Check now"}
          </button>
          ${i.ai_task_entity?V`
                <button
                  class="action"
                  ?disabled=${r}
                  @click=${()=>this._aiText(e,"generate_report")}
                >
                  ${ee(te)}${"generate_report"===n?"Writing report…":"Weekly report"}
                </button>
                <button
                  class="action"
                  ?disabled=${r}
                  @click=${()=>this._aiText(e,"explain_skips")}
                >
                  ${ee(te)}${"explain_skips"===n?"Explaining…":"Explain skips"}
                </button>
              `:I}
          <span class="spacer"></span>
          <button class="action" @click=${()=>this._editSchedule(e)}>
            ${ee(Kt)}Edit
          </button>
        </footer>
      </section>
    `;var h}_renderNextRun(t,e){return e.enabled?e.next_run?V`
      ${zt(t,e.next_run)}
      <span class="muted">(${Nt(e.next_run,this._now)})</span>
      ${!1===e.next_run_scheduled?V`<span class="chip" title="Waters only if a moisture sensor reads below the threshold"
            >moisture check</span
          >`:I}
      ${e.skip_next?V`<span class="chip warn">next watering skipped</span>`:I}
      ${e.paused?V`<span class="chip warn">paused</span>`:I}
    `:V`<span class="muted">Nothing scheduled</span>`:V`<span class="muted">Schedule is off</span>`}_renderRainDelay(t,e,i){const s=e.rain_delay_until;return V`
      ${s?V`<div>
            Until ${zt(t,s)}
            <span class="muted">(${Nt(s,this._now)})</span>
          </div>`:V`<div class="muted">None</div>`}
      <div class="inline-actions">
        ${ne.map(t=>V`<button
            class="mini"
            title=${`Skip scheduled runs for the next ${t} hours`}
            ?disabled=${i}
            @click=${()=>this._action(e,"set_rain_delay",{hours:t})}
          >
            ${t} h
          </button>`)}
        ${s?V`<button
              class="mini"
              ?disabled=${i}
              @click=${()=>this._action(e,"set_rain_delay",{hours:0})}
            >
              Clear
            </button>`:I}
      </div>
    `}_renderZones(t,e,i){const s=e.config??{},n=s.zones??[];return n.length?V`
      <ul class="zone-list">
        ${n.map(s=>V`<li>
            <span>${kt(t,s.entity_id)}</span>
            <span class="zone-controls">
              <span class="muted">${s.minutes} min</span>
              <button
                class="mini"
                title="Run only this zone"
                ?disabled=${i||e.running}
                @click=${()=>this._runZone(t,e,s)}
              >
                Run
              </button>
            </span>
          </li>`)}
      </ul>
      ${n.length>1?V`<div class="muted">${(t=>"concurrent"===t.zone_mode?"All zones at once":"One zone at a time")(s)}</div>`:I}
    `:V`<span class="muted">No zones</span>`}_renderRunning(t,e){let i=e.active_zones??[];return!i.length&&e.current_zone&&(i=[{entity_id:e.current_zone,ends_at:e.current_zone_ends_at}]),V`
      <div class="running-block">
        <div class="running-title">${ee(Gt)}Watering</div>
        ${i.length?i.map(e=>V`<div class="running-zone">
                <span>${kt(t,e.entity_id)}</span>
                <span class="countdown">
                  ${e.ends_at?`${((t,e)=>{const i=Math.max(0,Math.round((new Date(t).getTime()-e)/1e3)),s=Math.floor(i/3600),n=Math.floor(i%3600/60),r=i%60,o=t=>String(t).padStart(2,"0");return s>0?`${s}:${o(n)}:${o(r)}`:`${n}:${o(r)}`})(e.ends_at,this._now)} left`:"starting…"}
                </span>
              </div>`):V`<div class="muted">Starting…</div>`}
      </div>
    `}_renderLastRun(t,e){if(!e.last_run_start)return V`<span class="muted">Never</span>`;const i=e.last_run_total_minutes,s=e.zone_results??[];return V`
      <div>
        ${zt(t,e.last_run_start)}${e.last_run_end?` – ${Pt(t,e.last_run_end)}`:""}
      </div>
      ${null!=i?V`<div class="muted">${Mt(t,i,1)} min total</div>`:I}
      ${s.length?V`<ul class="zone-list">
            ${s.map(e=>V`<li class=${e.error?"error":""}>
                <span>
                  ${kt(t,e.entity_id)}
                  ${e.error?V`<span class="zone-error">${e.error}</span>`:I}
                </span>
                <span class=${e.error?"":"muted"}>${Mt(t,e.minutes,1)} min</span>
              </li>`)}
          </ul>`:I}
    `}_renderHistory(t,e,i){const s=this._histories[e.entry_id],n=s??e.history??[];return n.length?V`
      <ul class="history-list">
        ${n.map(e=>{const i="error"===e.status||(e.zones??[]).some(t=>t.error);return V`<li class=${i?"error":""}>
            <span>${((t,e)=>`${zt(t,e.at)} · ${At(e.status)}${e.manual?" (manual)":""}`)(t,e)}</span>
            <span class=${i?"":"muted"}>
              ${"run"===e.type?`${Mt(t,e.total_minutes??0,1)} min`:"skip"}
            </span>
          </li>`})}
      </ul>
      ${s?V`<button
            class="mini"
            @click=${()=>this._histories=oe(this._histories,e.entry_id)}
          >
            Show less
          </button>`:n.length>=10?V`<button class="mini" ?disabled=${i} @click=${()=>this._loadHistory(e)}>
              Show more
            </button>`:I}
    `:V`<span class="muted">No runs or skips yet</span>`}_renderEvaluation(t,e,i){return V`
      <div class="check-block">
        <div class="check-title">
          <span>Check at ${Pt(t,i.at)}</span>
          <button
            class="icon-button small"
            aria-label="Close check result"
            @click=${()=>this._evaluations=oe(this._evaluations,e.entry_id)}
          >
            ${ee(Xt)}
          </button>
        </div>
        ${((t,e)=>{const{decision:i}=e,s=[];return i.water?s.push({text:"Conditions allow watering now",tone:"ok"}):i.status?s.push({text:`Would skip: ${At(i.status)}`,tone:"warn"}):s.push({text:"Would not water: not a schedule day and no sensor is dry",tone:"muted"}),i.retry&&s.push({text:"Would re-check every 2 min until the maximum delay",tone:"info"}),e.scheduled||s.push({text:"Checked as a moisture check day",tone:"muted"}),e.rain_delay_until&&s.push({text:`Rain delay until ${zt(t,e.rain_delay_until)}: scheduled runs are skipped`,tone:"warn"}),e.paused&&s.push({text:"Paused: scheduled runs do nothing",tone:"warn"}),e.enabled||s.push({text:"Schedule is off",tone:"muted"}),[...s,...Vt(t,i.details)]})(t,i).map(t=>V`<div class="detail ${t.tone??""}">${t.text}</div>`)}
      </div>
    `}_renderDialog(){const t=this._dialog;return t?V`
      <div class="dialog-backdrop" @click=${this._closeDialog}>
        <div
          class="dialog"
          role="dialog"
          aria-modal="true"
          aria-label=${t.title}
          @click=${t=>t.stopPropagation()}
        >
          <h2>${t.title}</h2>
          <div class="dialog-text">${t.text}</div>
          <div class="dialog-actions">
            <button class="action filled" @click=${this._closeDialog}>Close</button>
          </div>
        </div>
      </div>
    `:I}_subscribe(){const t=this.hass;if(!t||!this.isConnected)return;if(this._connection===t.connection&&(this._unsubscribe||Date.now()-this._subscribeFailedAt<3e4))return;this._unsubscribeAll();const e=t.connection;this._connection=e,e.addEventListener("ready",this._handleReconnect);const i=e.subscribeMessage(t=>{this._schedules=t.schedules,this._loadError=void 0},{type:`${se}/subscribe`});this._unsubscribe=i,i.catch(t=>{this._unsubscribe===i&&(this._unsubscribe=void 0,this._subscribeFailedAt=Date.now(),this._loadError=`Could not load schedules: ${re(t)}`)})}_unsubscribeAll(){this._connection?.removeEventListener("ready",this._handleReconnect),this._connection=void 0;const t=this._unsubscribe;this._unsubscribe=void 0,t?.then(t=>t()).catch(()=>{})}async _refresh(){if(this.hass)try{const t=await this.hass.callWS({type:`${se}/schedules`});this._schedules=t.schedules,this._loadError=void 0}catch(t){}}_watchedEntities(){const t=new Set,e=e=>{e&&t.add(e)};for(const t of this._schedules??[]){const i=t.config??{};i.zones?.forEach(t=>e(t.entity_id)),i.moisture_sensors?.forEach(e),i.rain_sensors?.forEach(e),i.weather_entities?.forEach(e),i.occupancy_entities?.forEach(e),e(i.rain_sensor),e(i.weather_entity),e(i.temperature_sensor),e(i.wind_sensor);const s=t.last_details??{};e(s.moisture?.lowest_entity),(s.moisture?.unavailable_entities??[]).forEach(e),(s.occupancy?.occupied??[]).forEach(e),Object.keys(s.rain?.stations??{}).forEach(e),t.unclosed_zones?.forEach(e),t.zone_results?.forEach(t=>e(t.entity_id)),t.active_zones?.forEach(t=>e(t.entity_id))}return[...t]}_tick(){const t=Date.now();(this._schedules?.some(t=>t.running)||t-this._now>=3e4)&&(this._now=t)}async _request(t,e,i={}){const s=this.hass,n=t.entry_id;if(s&&void 0===this._pending[n]){this._pending={...this._pending,[n]:e},this._actionErrors=oe(this._actionErrors,n);try{return await s.callWS({type:`${se}/${e}`,entry_id:n,...i})}catch(t){return void(this._actionErrors={...this._actionErrors,[n]:re(t)})}finally{this._pending=oe(this._pending,n)}}}async _action(t,e,i={}){const s=await this._request(t,e,i);s&&this._schedules&&(this._schedules=this._schedules.map(e=>e.entry_id===t.entry_id?s:e))}async _evaluate(t){const e=await this._request(t,"evaluate");e&&(this._evaluations={...this._evaluations,[t.entry_id]:e})}async _loadHistory(t){const e=await this._request(t,"history",{limit:100});e&&(this._histories={...this._histories,[t.entry_id]:e.history})}async _aiText(t,e){const i=await this._request(t,e);i&&(this._dialog={title:"generate_report"===e?`${t.name}: weekly report`:`${t.name}: skipped runs`,text:i.text})}_runZone(t,e,i){const s=window.prompt(`Run ${kt(t,i.entity_id)} for how many minutes?`,String(i.minutes));if(null===s)return;const n=Number(s.trim());!Number.isInteger(n)||n<1||n>180?this._actionErrors={...this._actionErrors,[e.entry_id]:"Enter whole minutes from 1 to 180."}:this._action(e,"run_zone",{zone:i.entity_id,minutes:n})}async _globalAction(t){const e=this.hass;if(e&&void 0===this._globalPending&&("stop_all"!==t||window.confirm("Stop every active run?"))){this._globalPending=t,this._globalError=void 0;try{const i=await e.callWS({type:`${se}/${t}`});i?.schedules&&(this._schedules=i.schedules)}catch(t){this._globalError=re(t)}finally{this._globalPending=void 0}}}_toggleEnabled(t,e){const i=e.target,s=i.checked;i.checked=t.enabled,this._action(t,"set_enabled",{enabled:s})}_toggleMenu(){this.dispatchEvent(new CustomEvent("hass-toggle-menu",{bubbles:!0,composed:!0}))}_addSchedule(){ae(`/_my_redirect/config_flow_start?domain=${se}`)}_editSchedule(t){ae(`/config/integrations/integration/${se}#config_entry=${t.entry_id}`)}};le.styles=ie,t([dt({attribute:!1})],le.prototype,"hass",void 0),t([dt({type:Boolean,reflect:!0})],le.prototype,"narrow",void 0),t([dt({attribute:!1})],le.prototype,"route",void 0),t([dt({attribute:!1})],le.prototype,"panel",void 0),t([ht()],le.prototype,"_schedules",void 0),t([ht()],le.prototype,"_loadError",void 0),t([ht()],le.prototype,"_pending",void 0),t([ht()],le.prototype,"_actionErrors",void 0),t([ht()],le.prototype,"_evaluations",void 0),t([ht()],le.prototype,"_histories",void 0),t([ht()],le.prototype,"_globalPending",void 0),t([ht()],le.prototype,"_globalError",void 0),t([ht()],le.prototype,"_dialog",void 0),t([ht()],le.prototype,"_now",void 0),le=t([(t=>(e,i)=>{void 0!==i?i.addInitializer(()=>{customElements.define(t,e)}):customElements.define(t,e)})("irrigation-manager-panel")],le);export{le as IrrigationManagerPanel};
