function t(t,e,i,n){var s,r=arguments.length,o=r<3?e:null===n?n=Object.getOwnPropertyDescriptor(e,i):n;if("object"==typeof Reflect&&"function"==typeof Reflect.decorate)o=Reflect.decorate(t,e,i,n);else for(var a=t.length-1;a>=0;a--)(s=t[a])&&(o=(r<3?s(o):r>3?s(e,i,o):s(e,i))||o);return r>3&&o&&Object.defineProperty(e,i,o),o}"function"==typeof SuppressedError&&SuppressedError;const e=globalThis,i=e.ShadowRoot&&(void 0===e.ShadyCSS||e.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,n=Symbol(),s=new WeakMap;let r=class{constructor(t,e,i){if(this._$cssResult$=!0,i!==n)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o;const e=this.t;if(i&&void 0===t){const i=void 0!==e&&1===e.length;i&&(t=s.get(e)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),i&&s.set(e,t))}return t}toString(){return this.cssText}};const o=i?t=>t:t=>t instanceof CSSStyleSheet?(t=>{let e="";for(const i of t.cssRules)e+=i.cssText;return(t=>new r("string"==typeof t?t:t+"",void 0,n))(e)})(t):t,{is:a,defineProperty:l,getOwnPropertyDescriptor:d,getOwnPropertyNames:c,getOwnPropertySymbols:h,getPrototypeOf:u}=Object,p=globalThis,_=p.trustedTypes,g=_?_.emptyScript:"",$=p.reactiveElementPolyfillSupport,m=(t,e)=>t,f={toAttribute(t,e){switch(e){case Boolean:t=t?g:null;break;case Object:case Array:t=null==t?t:JSON.stringify(t)}return t},fromAttribute(t,e){let i=t;switch(e){case Boolean:i=null!==t;break;case Number:i=null===t?null:Number(t);break;case Object:case Array:try{i=JSON.parse(t)}catch(t){i=null}}return i}},b=(t,e)=>!a(t,e),y={attribute:!0,type:String,converter:f,reflect:!1,useDefault:!1,hasChanged:b};Symbol.metadata??=Symbol("metadata"),p.litPropertyMetadata??=new WeakMap;let v=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=y){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){const i=Symbol(),n=this.getPropertyDescriptor(t,i,e);void 0!==n&&l(this.prototype,t,n)}}static getPropertyDescriptor(t,e,i){const{get:n,set:s}=d(this.prototype,t)??{get(){return this[e]},set(t){this[e]=t}};return{get:n,set(e){const r=n?.call(this);s?.call(this,e),this.requestUpdate(t,r,i)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??y}static _$Ei(){if(this.hasOwnProperty(m("elementProperties")))return;const t=u(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(m("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(m("properties"))){const t=this.properties,e=[...c(t),...h(t)];for(const i of e)this.createProperty(i,t[i])}const t=this[Symbol.metadata];if(null!==t){const e=litPropertyMetadata.get(t);if(void 0!==e)for(const[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(const[t,e]of this.elementProperties){const i=this._$Eu(t,e);void 0!==i&&this._$Eh.set(i,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const e=[];if(Array.isArray(t)){const i=new Set(t.flat(1/0).reverse());for(const t of i)e.unshift(o(t))}else void 0!==t&&e.push(o(t));return e}static _$Eu(t,e){const i=e.attribute;return!1===i?void 0:"string"==typeof i?i:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){const t=new Map,e=this.constructor.elementProperties;for(const i of e.keys())this.hasOwnProperty(i)&&(t.set(i,this[i]),delete this[i]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return((t,n)=>{if(i)t.adoptedStyleSheets=n.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const i of n){const n=document.createElement("style"),s=e.litNonce;void 0!==s&&n.setAttribute("nonce",s),n.textContent=i.cssText,t.appendChild(n)}})(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,i){this._$AK(t,i)}_$ET(t,e){const i=this.constructor.elementProperties.get(t),n=this.constructor._$Eu(t,i);if(void 0!==n&&!0===i.reflect){const s=(void 0!==i.converter?.toAttribute?i.converter:f).toAttribute(e,i.type);this._$Em=t,null==s?this.removeAttribute(n):this.setAttribute(n,s),this._$Em=null}}_$AK(t,e){const i=this.constructor,n=i._$Eh.get(t);if(void 0!==n&&this._$Em!==n){const t=i.getPropertyOptions(n),s="function"==typeof t.converter?{fromAttribute:t.converter}:void 0!==t.converter?.fromAttribute?t.converter:f;this._$Em=n;const r=s.fromAttribute(e,t.type);this[n]=r??this._$Ej?.get(n)??r,this._$Em=null}}requestUpdate(t,e,i){if(void 0!==t){const n=this.constructor,s=this[t];if(i??=n.getPropertyOptions(t),!((i.hasChanged??b)(s,e)||i.useDefault&&i.reflect&&s===this._$Ej?.get(t)&&!this.hasAttribute(n._$Eu(t,i))))return;this.C(t,e,i)}!1===this.isUpdatePending&&(this._$ES=this._$EP())}C(t,e,{useDefault:i,reflect:n,wrapped:s},r){i&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,r??e??this[t]),!0!==s||void 0!==r)||(this._$AL.has(t)||(this.hasUpdated||i||(e=void 0),this._$AL.set(t,e)),!0===n&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[t,e]of this._$Ep)this[t]=e;this._$Ep=void 0}const t=this.constructor.elementProperties;if(t.size>0)for(const[e,i]of t){const{wrapped:t}=i,n=this[e];!0!==t||this._$AL.has(e)||void 0===n||this.C(e,void 0,i,n)}}let t=!1;const e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(e){throw t=!1,this._$EM(),e}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(t){}firstUpdated(t){}};v.elementStyles=[],v.shadowRootOptions={mode:"open"},v[m("elementProperties")]=new Map,v[m("finalized")]=new Map,$?.({ReactiveElement:v}),(p.reactiveElementVersions??=[]).push("2.1.1");const x=globalThis,w=x.trustedTypes,k=w?w.createPolicy("lit-html",{createHTML:t=>t}):void 0,A="$lit$",E=`lit$${Math.random().toFixed(9).slice(2)}$`,S="?"+E,C=`<${S}>`,z=document,M=()=>z.createComment(""),H=t=>null===t||"object"!=typeof t&&"function"!=typeof t,R=Array.isArray,L="[ \t\n\f\r]",P=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,D=/-->/g,N=/>/g,O=RegExp(`>|${L}(?:([^\\s"'>=/]+)(${L}*=${L}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,"g"),U=/'/g,T=/"/g,V=/^(?:script|style|textarea|title)$/i,j=(t=>(e,...i)=>({_$litType$:t,strings:e,values:i}))(1),I=Symbol.for("lit-noChange"),Z=Symbol.for("lit-nothing"),q=new WeakMap,W=z.createTreeWalker(z,129);function B(t,e){if(!R(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==k?k.createHTML(e):e}const F=(t,e)=>{const i=t.length-1,n=[];let s,r=2===e?"<svg>":3===e?"<math>":"",o=P;for(let e=0;e<i;e++){const i=t[e];let a,l,d=-1,c=0;for(;c<i.length&&(o.lastIndex=c,l=o.exec(i),null!==l);)c=o.lastIndex,o===P?"!--"===l[1]?o=D:void 0!==l[1]?o=N:void 0!==l[2]?(V.test(l[2])&&(s=RegExp("</"+l[2],"g")),o=O):void 0!==l[3]&&(o=O):o===O?">"===l[0]?(o=s??P,d=-1):void 0===l[1]?d=-2:(d=o.lastIndex-l[2].length,a=l[1],o=void 0===l[3]?O:'"'===l[3]?T:U):o===T||o===U?o=O:o===D||o===N?o=P:(o=O,s=void 0);const h=o===O&&t[e+1].startsWith("/>")?" ":"";r+=o===P?i+C:d>=0?(n.push(a),i.slice(0,d)+A+i.slice(d)+E+h):i+E+(-2===d?e:h)}return[B(t,r+(t[i]||"<?>")+(2===e?"</svg>":3===e?"</math>":"")),n]};class K{constructor({strings:t,_$litType$:e},i){let n;this.parts=[];let s=0,r=0;const o=t.length-1,a=this.parts,[l,d]=F(t,e);if(this.el=K.createElement(l,i),W.currentNode=this.el.content,2===e||3===e){const t=this.el.content.firstChild;t.replaceWith(...t.childNodes)}for(;null!==(n=W.nextNode())&&a.length<o;){if(1===n.nodeType){if(n.hasAttributes())for(const t of n.getAttributeNames())if(t.endsWith(A)){const e=d[r++],i=n.getAttribute(t).split(E),o=/([.?@])?(.*)/.exec(e);a.push({type:1,index:s,name:o[2],strings:i,ctor:"."===o[1]?Y:"?"===o[1]?tt:"@"===o[1]?et:X}),n.removeAttribute(t)}else t.startsWith(E)&&(a.push({type:6,index:s}),n.removeAttribute(t));if(V.test(n.tagName)){const t=n.textContent.split(E),e=t.length-1;if(e>0){n.textContent=w?w.emptyScript:"";for(let i=0;i<e;i++)n.append(t[i],M()),W.nextNode(),a.push({type:2,index:++s});n.append(t[e],M())}}}else if(8===n.nodeType)if(n.data===S)a.push({type:2,index:s});else{let t=-1;for(;-1!==(t=n.data.indexOf(E,t+1));)a.push({type:7,index:s}),t+=E.length-1}s++}}static createElement(t,e){const i=z.createElement("template");return i.innerHTML=t,i}}function G(t,e,i=t,n){if(e===I)return e;let s=void 0!==n?i._$Co?.[n]:i._$Cl;const r=H(e)?void 0:e._$litDirective$;return s?.constructor!==r&&(s?._$AO?.(!1),void 0===r?s=void 0:(s=new r(t),s._$AT(t,i,n)),void 0!==n?(i._$Co??=[])[n]=s:i._$Cl=s),void 0!==s&&(e=G(t,s._$AS(t,e.values),s,n)),e}let J=class{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:e},parts:i}=this._$AD,n=(t?.creationScope??z).importNode(e,!0);W.currentNode=n;let s=W.nextNode(),r=0,o=0,a=i[0];for(;void 0!==a;){if(r===a.index){let e;2===a.type?e=new Q(s,s.nextSibling,this,t):1===a.type?e=new a.ctor(s,a.name,a.strings,this,t):6===a.type&&(e=new it(s,this,t)),this._$AV.push(e),a=i[++o]}r!==a?.index&&(s=W.nextNode(),r++)}return W.currentNode=z,n}p(t){let e=0;for(const i of this._$AV)void 0!==i&&(void 0!==i.strings?(i._$AI(t,i,e),e+=i.strings.length-2):i._$AI(t[e])),e++}};class Q{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,i,n){this.type=2,this._$AH=Z,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=i,this.options=n,this._$Cv=n?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode;const e=this._$AM;return void 0!==e&&11===t?.nodeType&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=G(this,t,e),H(t)?t===Z||null==t||""===t?(this._$AH!==Z&&this._$AR(),this._$AH=Z):t!==this._$AH&&t!==I&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):(t=>R(t)||"function"==typeof t?.[Symbol.iterator])(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==Z&&H(this._$AH)?this._$AA.nextSibling.data=t:this.T(z.createTextNode(t)),this._$AH=t}$(t){const{values:e,_$litType$:i}=t,n="number"==typeof i?this._$AC(t):(void 0===i.el&&(i.el=K.createElement(B(i.h,i.h[0]),this.options)),i);if(this._$AH?._$AD===n)this._$AH.p(e);else{const t=new J(n,this),i=t.u(this.options);t.p(e),this.T(i),this._$AH=t}}_$AC(t){let e=q.get(t.strings);return void 0===e&&q.set(t.strings,e=new K(t)),e}k(t){R(this._$AH)||(this._$AH=[],this._$AR());const e=this._$AH;let i,n=0;for(const s of t)n===e.length?e.push(i=new Q(this.O(M()),this.O(M()),this,this.options)):i=e[n],i._$AI(s),n++;n<e.length&&(this._$AR(i&&i._$AB.nextSibling,n),e.length=n)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){const e=t.nextSibling;t.remove(),t=e}}setConnected(t){void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t))}}class X{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,i,n,s){this.type=1,this._$AH=Z,this._$AN=void 0,this.element=t,this.name=e,this._$AM=n,this.options=s,i.length>2||""!==i[0]||""!==i[1]?(this._$AH=Array(i.length-1).fill(new String),this.strings=i):this._$AH=Z}_$AI(t,e=this,i,n){const s=this.strings;let r=!1;if(void 0===s)t=G(this,t,e,0),r=!H(t)||t!==this._$AH&&t!==I,r&&(this._$AH=t);else{const n=t;let o,a;for(t=s[0],o=0;o<s.length-1;o++)a=G(this,n[i+o],e,o),a===I&&(a=this._$AH[o]),r||=!H(a)||a!==this._$AH[o],a===Z?t=Z:t!==Z&&(t+=(a??"")+s[o+1]),this._$AH[o]=a}r&&!n&&this.j(t)}j(t){t===Z?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}}class Y extends X{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===Z?void 0:t}}class tt extends X{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==Z)}}class et extends X{constructor(t,e,i,n,s){super(t,e,i,n,s),this.type=5}_$AI(t,e=this){if((t=G(this,t,e,0)??Z)===I)return;const i=this._$AH,n=t===Z&&i!==Z||t.capture!==i.capture||t.once!==i.once||t.passive!==i.passive,s=t!==Z&&(i===Z||n);n&&this.element.removeEventListener(this.name,this,i),s&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}}class it{constructor(t,e,i){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=i}get _$AU(){return this._$AM._$AU}_$AI(t){G(this,t)}}const nt={I:Q},st=x.litHtmlPolyfillSupport;st?.(K,Q),(x.litHtmlVersions??=[]).push("3.3.1");const rt=globalThis;let ot=class extends v{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=((t,e,i)=>{const n=i?.renderBefore??e;let s=n._$litPart$;if(void 0===s){const t=i?.renderBefore??null;n._$litPart$=s=new Q(e.insertBefore(M(),t),t,void 0,i??{})}return s._$AI(t),s})(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return I}};ot._$litElement$=!0,ot.finalized=!0,rt.litElementHydrateSupport?.({LitElement:ot});const at=rt.litElementPolyfillSupport;at?.({LitElement:ot}),(rt.litElementVersions??=[]).push("4.2.1");const lt={attribute:!0,type:String,converter:f,reflect:!1,hasChanged:b},dt=(t=lt,e,i)=>{const{kind:n,metadata:s}=i;let r=globalThis.litPropertyMetadata.get(s);if(void 0===r&&globalThis.litPropertyMetadata.set(s,r=new Map),"setter"===n&&((t=Object.create(t)).wrapped=!0),r.set(i.name,t),"accessor"===n){const{name:n}=i;return{set(i){const s=e.get.call(this);e.set.call(this,i),this.requestUpdate(n,s,t)},init(e){return void 0!==e&&this.C(n,void 0,t,e),e}}}if("setter"===n){const{name:n}=i;return function(i){const s=this[n];e.call(this,i),this.requestUpdate(n,s,t)}}throw Error("Unsupported decorator location: "+n)};function ct(t){return(e,i)=>"object"==typeof i?dt(t,e,i):((t,e,i)=>{const n=e.hasOwnProperty(i);return e.constructor.createProperty(i,t),n?Object.getOwnPropertyDescriptor(e,i):void 0})(t,e,i)}function ht(t){return ct({...t,state:!0,attribute:!1})}const ut=2;class pt{constructor(t){}get _$AU(){return this._$AM._$AU}_$AT(t,e,i){this._$Ct=t,this._$AM=e,this._$Ci=i}_$AS(t,e){return this.update(t,e)}update(t,e){return this.render(...e)}}const{I:_t}=nt,gt=()=>document.createComment(""),$t=(t,e,i)=>{const n=t._$AA.parentNode,s=void 0===e?t._$AB:e._$AA;if(void 0===i){const e=n.insertBefore(gt(),s),r=n.insertBefore(gt(),s);i=new _t(e,r,t,t.options)}else{const e=i._$AB.nextSibling,r=i._$AM,o=r!==t;if(o){let e;i._$AQ?.(t),i._$AM=t,void 0!==i._$AP&&(e=t._$AU)!==r._$AU&&i._$AP(e)}if(e!==s||o){let t=i._$AA;for(;t!==e;){const e=t.nextSibling;n.insertBefore(t,s),t=e}}}return i},mt=(t,e,i=t)=>(t._$AI(e,i),t),ft={},bt=t=>{t._$AR(),t._$AA.remove()},yt=(t,e,i)=>{const n=new Map;for(let s=e;s<=i;s++)n.set(t[s],s);return n},vt=(t=>(...e)=>({_$litDirective$:t,values:e}))(class extends pt{constructor(t){if(super(t),t.type!==ut)throw Error("repeat() can only be used in text expressions")}dt(t,e,i){let n;void 0===i?i=e:void 0!==e&&(n=e);const s=[],r=[];let o=0;for(const e of t)s[o]=n?n(e,o):o,r[o]=i(e,o),o++;return{values:r,keys:s}}render(t,e,i){return this.dt(t,e,i).values}update(t,[e,i,n]){const s=(t=>t._$AH)(t),{values:r,keys:o}=this.dt(e,i,n);if(!Array.isArray(s))return this.ut=o,r;const a=this.ut??=[],l=[];let d,c,h=0,u=s.length-1,p=0,_=r.length-1;for(;h<=u&&p<=_;)if(null===s[h])h++;else if(null===s[u])u--;else if(a[h]===o[p])l[p]=mt(s[h],r[p]),h++,p++;else if(a[u]===o[_])l[_]=mt(s[u],r[_]),u--,_--;else if(a[h]===o[_])l[_]=mt(s[h],r[_]),$t(t,l[_+1],s[h]),h++,_--;else if(a[u]===o[p])l[p]=mt(s[u],r[p]),$t(t,s[h],s[u]),u--,p++;else if(void 0===d&&(d=yt(o,p,_),c=yt(a,h,u)),d.has(a[h]))if(d.has(a[u])){const e=c.get(o[p]),i=void 0!==e?s[e]:null;if(null===i){const e=$t(t,s[h]);mt(e,r[p]),l[p]=e}else l[p]=mt(i,r[p]),$t(t,s[h],i),s[e]=null;p++}else bt(s[u]),u--;else bt(s[h]),h++;for(;p<=_;){const e=$t(t,l[_+1]);mt(e,r[p]),l[p++]=e}for(;h<=u;){const t=s[h++];null!==t&&bt(t)}return this.ut=o,((t,e=ft)=>{t._$AH=e})(t,l),I}}),xt=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],wt={idle:{label:"Idle",tone:"muted"},running:{label:"Running",tone:"info"},disabled:{label:"Disabled",tone:"muted"},paused:{label:"Paused",tone:"muted"},skipped_rain:{label:"Skipped: rain",tone:"warn"},skipped_forecast:{label:"Skipped: forecast",tone:"warn"},skipped_temperature:{label:"Skipped: temperature",tone:"warn"},skipped_wind:{label:"Skipped: wind",tone:"warn"},skipped_occupancy:{label:"Skipped: occupied",tone:"warn"},skipped_moisture:{label:"Skipped: soil moisture",tone:"warn"},skipped_rain_delay:{label:"Skipped: rain delay",tone:"warn"},skipped_manual:{label:"Skipped: manual",tone:"warn"},skipped_busy:{label:"Skipped: still running",tone:"warn"},stopped_rain:{label:"Stopped: rain started",tone:"warn"},stopped_occupancy:{label:"Stopped: occupied",tone:"warn"},interrupted:{label:"Interrupted",tone:"error"},error:{label:"Error",tone:"error"}},kt=t=>wt[t]?.label??t,At=(t,e)=>e?t.states[e]?.attributes.friendly_name??e:"",Et=(t,e)=>e.map(e=>At(t,e)).join(", "),St=/\(?\s*-?\d{1,3}\.\d{2,}\s*,\s*-?\d{1,3}\.\d{2,}\s*\)?/g,Ct=(t,e)=>At(t,e).replace(St," ").replace(/\s+([:,])/g,"$1").replace(/\s{2,}/g," ").replace(/^[\s:,–-]+|[\s:,–-]+$/g,"")||(e??""),zt=(t,e)=>{const i=t.states[e??""]?.attributes.unit_of_measurement;return i?` ${i}`:""},Mt=t=>t.locale?.language??t.language??"en",Ht=t=>{const e={};return"local"!==t.locale?.time_zone&&t.config?.time_zone&&(e.timeZone=t.config.time_zone),"12"===t.locale?.time_format?e.hour12=!0:"24"===t.locale?.time_format&&(e.hour12=!1),e},Rt=(t,e,i=2)=>Number(e).toLocaleString(Mt(t),{maximumFractionDigits:i}),Lt=(t,e)=>new Date(e).toLocaleString(Mt(t),{...Ht(t),weekday:"short",month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}),Pt=(t,e)=>new Date(e).toLocaleTimeString(Mt(t),{...Ht(t),hour:"numeric",minute:"2-digit"}),Dt=(t,e)=>{const[i,n]=e.split(":").map(Number);if(Number.isNaN(i)||Number.isNaN(n))return e;const{hour12:s}=Ht(t);return new Date(2e3,0,1,i,n).toLocaleTimeString(Mt(t),{hour:"numeric",minute:"2-digit",...void 0===s?{}:{hour12:s}})},Nt=(t,e)=>`${t} ${e}${1===t?"":"s"}`,Ot=t=>{const e=Math.floor(t/1440),i=Math.floor(t%1440/60),n=t%60;return e>0?i>0?`${e} d ${i} h`:`${e} d`:i>0?n>0?`${i} h ${n} min`:`${i} h`:`${n} min`},Ut=(t,e)=>{const i=Math.round((new Date(t).getTime()-e)/6e4);return 0===i?"now":i>0?`in ${Ot(i)}`:`${Ot(-i)} ago`},Tt=(t,e)=>{if("hourly"===e.frequency){const i=e.interval_hours??1,n=1===i?"Every hour":`Every ${i} hours`;return e.window_start&&e.window_end?`${n}, ${Dt(t,e.window_start)}–${Dt(t,e.window_end)}`:n}if("interval"===e.frequency){const i=e.interval_days??1,n=1===i?"Every day":`Every ${i} days`;return e.anchor?`${n} from ${((t,e)=>{const[i,n,s]=e.split("-").map(Number);return i&&n&&s?new Date(i,n-1,s).toLocaleDateString(Mt(t),{weekday:"short",month:"short",day:"numeric",year:"numeric"}):e})(t,e.anchor)}`:n}const i=[...e.weekdays??[]].sort((t,e)=>t-e);return 7===i.length?"Every day":i.length?i.map(t=>xt[t]??String(t)).join(", "):"No days"},Vt=t=>t.weather_entities?.length?t.weather_entities:t.weather_entity?[t.weather_entity]:[],jt=t=>null!=t,It=(t,e)=>{const i=e.skip_conditions??[],n=[];if(i.includes("rain")){const i=(t=>t.rain_sensors?.length?t.rain_sensors:t.rain_sensor?[t.rain_sensor]:[])(e),s=zt(t,i[0]),r="since_last_watering"===e.rain_window?`since the last watering (at most ${Nt(e.rain_max_hours??168,"hour")})`:`in the last ${Nt(e.rain_hours??24,"hour")}`;let o;o=i.length<=1?Ct(t,i[0]):"median"===e.rain_aggregate?`median of ${i.length} stations`:"quorum"===e.rain_aggregate?`at least ${e.rain_quorum??2} of ${i.length} stations`:`any of ${i.length} stations`,n.push(`Skip if ≥ ${Rt(t,e.rain_threshold??0)}${s} of rain ${r} (${o})`);const a=e.rain_delay_auto_hours??0;a>0&&n.push(`After a rain skip, delay watering ${Nt(a,"hour")}`),e.rain_stop_during_run&&n.push(`Stop a run when ${Rt(t,e.rain_stop_amount??.05)}${s} of new rain falls`)}if(i.includes("forecast")){const i=Vt(e),s=`the rain chance is ≥ ${e.forecast_probability??0}%`,r=`the forecast rain is ≥ ${Rt(t,e.forecast_amount??0)}`,o=e.forecast_mode??"probability",a="amount"===o?r:"either"===o?`${s} or ${r}`:"both"===o?`${s} and ${r}`:s,l=Math.min(e.forecast_quorum??1,Math.max(i.length,1)),d=i.length<=1?Ct(t,i[0]):l<=1?`any of ${i.length} forecasts`:`${l} of ${i.length} forecasts`;n.push(`Skip if ${a} in the next ${Nt(e.forecast_hours??12,"hour")} (${d})`)}if(i.includes("temperature")){const i=t.states[e.temperature_sensor??""]?.attributes.unit_of_measurement??"°",s=e.temperature_forecast_hours??12,r=[];if(jt(e.temperature_min)){const n=s>0&&Vt(e).length?` (or the forecast low in the next ${Nt(s,"hour")})`:"";r.push(`at or below ${Rt(t,e.temperature_min,1)}${i}${n}`)}if(jt(e.temperature_max)&&r.push(`at or above ${Rt(t,e.temperature_max,1)}${i}`),r.length){const i=e.temperature_sensor?` (${Ct(t,e.temperature_sensor)})`:"";n.push(`Skip if the temperature is ${r.join(" or ")}${i}`)}(e.stale_hours??0)>0&&n.push(`Ignore a temperature reading older than ${Nt(e.stale_hours??0,"hour")}`)}if(i.includes("wind")&&n.push(`Skip if the average wind over ${e.wind_minutes??30} min is ≥ ${Rt(t,e.wind_max??0,1)}${zt(t,e.wind_sensor)} (${Ct(t,e.wind_sensor)})`),i.includes("occupancy")){const i=((t,e)=>e.map(e=>Ct(t,e)).join(", "))(t,e.occupancy_entities??[])||"an occupancy entity";n.push("skip"===e.occupancy_action?`Skip while ${i} is on`:`Wait up to ${e.occupancy_max_delay_minutes??60} min while ${i} is on, then skip`),e.occupancy_stop_during_run&&n.push("Stop a run when an occupancy entity turns on")}if(i.includes("moisture")){const i=e.moisture_sensors??[],s=1===i.length?Ct(t,i[0]):`any of ${i.length} sensors`,r=Rt(t,e.moisture_threshold??0,1);if("trigger"===e.moisture_mode)n.push(`Also waters on other days when ${s} reads below ${r}%`);else{const t="skip"===e.moisture_unavailable?"skip":"water anyway";n.push(`Only waters when ${s} reads below ${r}% (no readings: ${t})`)}}return n},Zt=(t,e)=>({text:`${t}: no data${e.reason?` (${e.reason})`:""}`,tone:"muted"}),qt=(t,e)=>{const i=e??{},n=[];return i.manual&&n.push({text:"Started manually"}),n.push(...((t,e)=>{if(!e)return[];if(!jt(e.total))return[Zt("Rain",e)];const i=e.unit?` ${e.unit}`:"",n=`${Rt(t,e.threshold??0)}${i}`,s="since_last_watering"===e.window&&e.window_start?`since ${Lt(t,e.window_start)}`:`in the last ${Nt(e.hours??0,"hour")}`,r=e.stations,o=[];if(r&&"quorum"===e.aggregate){const t=(e.stations_over??0)>=(e.quorum??1);o.push({text:`Rain ${s}: ${e.stations_over??0} of ${e.stations_reporting??0} stations ≥ ${n} (need ${e.quorum??1})`,tone:t?"warn":void 0})}else{const a=r?"median"===e.aggregate?"Median rain":"Most rain":"Rain",l=jt(e.threshold)&&e.total>=e.threshold;o.push({text:`${a} ${Rt(t,e.total)}${i} ${s} ${l?"≥":"<"} ${n}`,tone:l?"warn":void 0})}return r&&o.push({text:Object.entries(r).map(([e,n])=>`${At(t,e)}: ${jt(n.total)?`${Rt(t,n.total)}${i}`:"no data"}`).join(" · "),tone:"muted"}),o})(t,i.rain),...((t,e)=>{if(!e)return[];const i=jt(e.max_probability),n=jt(e.amount);if(!i&&!n)return[Zt("Forecast",e)];const s=e.mode??"probability",r=[];if(i&&"amount"!==s){const i=jt(e.threshold)&&e.max_probability>=e.threshold,n=e.at?` at ${Lt(t,e.at)}`:"";r.push({text:`Forecast ${e.max_probability}% rain chance${n} ${i?"≥":"<"} ${e.threshold}%`+(e.forecast_type?` (${String(e.forecast_type).replace("_"," ")})`:""),tone:i?"warn":void 0})}if(n&&"probability"!==s){const i=e.amount_unit?` ${e.amount_unit}`:"",n=jt(e.amount_threshold)&&e.amount>=e.amount_threshold;r.push({text:`Forecast rain ${Rt(t,e.amount)}${i} in the next ${Nt(e.hours??0,"hour")} ${n?"≥":"<"} ${Rt(t,e.amount_threshold??0)}${i}`,tone:n?"warn":void 0})}if(e.entities){const t=(e.entities_triggering??0)>=(e.quorum??1);r.push({text:`${e.entities_triggering??0} of ${e.entities_available??0} forecasts reached the limit (need ${e.quorum??1})`,tone:t?"warn":"muted"})}return r})(t,i.forecast),...((t,e)=>{if(!e)return[];const i=jt(e.current),n=jt(e.forecast_low);if(!i&&!n)return[Zt("Temperature",e)];const s=e.unit??"",r=[];i&&r.push(`${Rt(t,e.current,1)}${s} now`),n&&r.push(`forecast low ${Rt(t,e.forecast_low,1)}${s}`);const o=[];jt(e.min)&&o.push(`min ${Rt(t,e.min,1)}${s}`),jt(e.max)&&o.push(`max ${Rt(t,e.max,1)}${s}`);const a=[{text:`Temperature ${r.join(", ")}`+(o.length?` (${o.join(", ")})`:"")+({freeze:" — at or below the minimum",freeze_forecast:" — forecast low at or below the minimum",heat:" — at or above the maximum"}[e.trigger]??""),tone:e.trigger?"warn":void 0}];return e.sensor_reason&&a.push({text:`Temperature sensor: ${e.sensor_reason}`,tone:"muted"}),a})(t,i.temperature),...((t,e)=>{if(!e)return[];if(!jt(e.average))return[Zt("Wind",e)];const i=e.unit?` ${e.unit}`:"",n=jt(e.max)&&e.average>=e.max;return[{text:`Wind ${Rt(t,e.average,1)}${i} average over ${e.minutes??0} min ${n?"≥":"<"} ${Rt(t,e.max??0,1)}${i}`,tone:n?"warn":void 0}]})(t,i.wind),...((t,e)=>{if(!e)return[];if(e.reason)return[Zt("Occupancy",e)];const i=e.occupied??[];return i.length?[{text:`Occupied: ${Et(t,i)}`,tone:"warn"}]:[{text:"Not occupied",tone:"muted"}]})(t,i.occupancy),...((t,e)=>{if(!e)return[];const i=[];if(jt(e.lowest)){const n=jt(e.threshold)&&e.lowest<e.threshold;i.push({text:`Lowest moisture ${Rt(t,e.lowest,1)}% (${At(t,e.lowest_entity)}) ${n?"<":"≥"} ${Rt(t,e.threshold??0,1)}%`})}else i.push(Zt("Soil moisture",e));const n=e.unavailable_entities??[];return n.length&&i.push({text:`No reading from ${Et(t,n)}`,tone:"muted"}),i})(t,i.moisture)),i.occupancy_delay_until&&n.push({text:`Waiting for occupancy to clear, up to ${Lt(t,i.occupancy_delay_until)}`,tone:"info"}),i.skipped_busy_at&&n.push({text:`Skipped a start at ${Lt(t,i.skipped_busy_at)} because a run was still going`,tone:"warn"}),i.error&&n.push({text:String(i.error),tone:"error"}),n},Wt="M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z",Bt="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z",Ft="M8,5.14V19.14L19,12.14L8,5.14Z",Kt="M18,18H6V6H18V18Z",Gt="M16,18H18V6H16M6,18L14.5,12L6,6V18Z",Jt="M12.5,8C9.85,8 7.45,9 5.6,10.6L2,7V16H11L7.38,12.38C8.77,11.22 10.54,10.5 12.5,10.5C16.04,10.5 19.05,12.81 20.1,16L22.47,15.22C21.08,11.03 17.15,8 12.5,8Z",Qt="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z",Xt="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z",Yt="M12,20A6,6 0 0,1 6,14C6,10 12,3.25 12,3.25C12,3.25 18,10 18,14A6,6 0 0,1 12,20Z",te="M14,19H18V5H14M6,19H10V5H6V19Z",ee="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z",ie="M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z",ne="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z",se="M13,14H11V10H13M13,18H11V16H13M1,21H23L12,2L1,21Z",re="M12,2A2,2 0 0,1 14,4C14,4.74 13.6,5.39 13,5.73V7H14A7,7 0 0,1 21,14H22A1,1 0 0,1 23,15V18A1,1 0 0,1 22,19H21V20A2,2 0 0,1 19,22H5A2,2 0 0,1 3,20V19H2A1,1 0 0,1 1,18V15A1,1 0 0,1 2,14H3A7,7 0 0,1 10,7H11V5.73C10.4,5.39 10,4.74 10,4A2,2 0 0,1 12,2M7.5,13A2.5,2.5 0 0,0 5,15.5A2.5,2.5 0 0,0 7.5,18A2.5,2.5 0 0,0 10,15.5A2.5,2.5 0 0,0 7.5,13M16.5,13A2.5,2.5 0 0,0 14,15.5A2.5,2.5 0 0,0 16.5,18A2.5,2.5 0 0,0 19,15.5A2.5,2.5 0 0,0 16.5,13Z",oe=t=>j`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d=${t}></path></svg>`,ae=((t,...e)=>{const i=1===t.length?t[0]:e.reduce((e,i,n)=>e+(t=>{if(!0===t._$cssResult$)return t.cssText;if("number"==typeof t)return t;throw Error("Value passed to 'css' function must be a 'css' function result: "+t+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+t[n+1],t[0]);return new r(i,t,n)})`
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

  .details summary {
    display: flex;
    align-items: center;
    gap: 4px;
    width: fit-content;
    margin: 0 16px 8px;
    color: var(--secondary-text-color, #727272);
    font-size: 14px;
    cursor: pointer;
    list-style: none;
  }

  .details summary::-webkit-details-marker {
    display: none;
  }

  .details summary .icon {
    transition: transform 0.2s;
  }

  .details[open] summary .icon {
    transform: rotate(180deg);
  }

  .details summary:focus-visible {
    outline: 2px solid var(--primary-color, #03a9f4);
    outline-offset: 2px;
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

  .zone-link {
    padding: 0;
    border: none;
    background: transparent;
    color: var(--primary-color, #03a9f4);
    text-align: left;
    cursor: pointer;
  }

  .zone-link:hover {
    text-decoration: underline;
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
    gap: 8px;
    padding: 16px 24px 20px;
  }

  .run-zones {
    display: grid;
    gap: 8px;
    margin: 0;
    padding: 16px 24px 0;
    overflow: auto;
    list-style: none;
  }

  .run-zones li {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 80px auto;
    align-items: center;
    gap: 8px;
  }

  .run-zones input {
    box-sizing: border-box;
    width: 100%;
    padding: 6px 8px;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 8px;
    background: transparent;
    color: inherit;
    font: inherit;
  }

  .dialog-error {
    margin: 12px 24px 0;
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
`,le="irrigation_manager",de=[24,48,72],ce=180,he=t=>{if(t&&"object"==typeof t){if("message"in t)return String(t.message);if("error"in t)return he(t.error)}return String(t)},ue=(t,e)=>{const{[e]:i,...n}=t;return n},pe=t=>{history.pushState(null,"",t),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}}))};let _e=class extends ot{constructor(){super(...arguments),this.narrow=!1,this._pending={},this._actionErrors={},this._evaluations={},this._histories={},this._now=Date.now(),this._subscribeFailedAt=0,this._handleReconnect=()=>{if(!this._unsubscribe)return this._subscribeFailedAt=0,void this._subscribe();this._refresh()},this._closeDialog=()=>{this._dialog=void 0},this._closeRunDialog=()=>{this._runDialog=void 0},this._handleKeydown=t=>{"Escape"===t.key&&(this._dialog||this._runDialog)&&(this._dialog=void 0,this._runDialog=void 0)}}connectedCallback(){super.connectedCallback(),this._subscribe(),this._timer=window.setInterval(()=>this._tick(),1e3),window.addEventListener("keydown",this._handleKeydown)}disconnectedCallback(){super.disconnectedCallback(),window.clearInterval(this._timer),this._timer=void 0,window.removeEventListener("keydown",this._handleKeydown),this._unsubscribeAll()}shouldUpdate(t){if(this._subscribe(),1!==t.size||!t.has("hass"))return!0;const e=t.get("hass"),i=this.hass;return!(e&&i&&this._schedules)||(e.locale!==i.locale||e.language!==i.language||e.config!==i.config||e.dockedSidebar!==i.dockedSidebar||this._watchedEntities().some(t=>e.states[t]!==i.states[t]))}render(){const t=this.hass,e=this.narrow||"always_hidden"===t?.dockedSidebar;return j`
      <div class="toolbar">
        ${e?j`<button class="icon-button" aria-label="Show sidebar" @click=${this._toggleMenu}>
              ${oe(Wt)}
            </button>`:Z}
        <div class="title">Irrigation</div>
        <button class="toolbar-button" @click=${this._addSchedule}>
          ${oe(Bt)}<span>Add schedule</span>
        </button>
      </div>
      <main class="content">
        ${this._loadError?j`<div class="banner error" role="alert">${this._loadError}</div>`:Z}
        ${this._renderGlobal()}
        ${this._renderBody(t)}
      </main>
      ${this._renderDialog()} ${this._renderRunDialog()}
    `}_renderGlobal(){const t=this._schedules??[];if(!t.length)return Z;const e=t.filter(t=>t.paused).length,i=t.some(t=>t.running),n=void 0!==this._globalPending;return j`
      ${e?j`<div class="banner warn" role="status">
            ${oe(te)}${e===t.length?"All schedules are paused. Scheduled runs do nothing until you resume.":`${e} of ${t.length} schedules are paused.`}
          </div>`:Z}
      ${this._globalError?j`<div class="banner error" role="alert">${this._globalError}</div>`:Z}
      <div class="global-actions">
        ${e<t.length?j`<button
              class="action"
              ?disabled=${n}
              @click=${()=>this._globalAction("pause_all")}
            >
              ${oe(te)}Pause all
            </button>`:Z}
        ${e?j`<button
              class="action"
              ?disabled=${n}
              @click=${()=>this._globalAction("resume_all")}
            >
              ${oe(Ft)}Resume all
            </button>`:Z}
        ${i?j`<button
              class="action danger"
              ?disabled=${n}
              @click=${()=>this._globalAction("stop_all")}
            >
              ${oe(Kt)}Stop all
            </button>`:Z}
      </div>
    `}_renderBody(t){return t&&void 0!==this._schedules?0===this._schedules.length?j`
        <div class="empty">
          <div class="empty-icon">${oe(Yt)}</div>
          <h2>No schedules yet</h2>
          <p>
            Add a schedule to choose valves or switches, set when they water, and pick
            rain, forecast, temperature, wind, occupancy or soil moisture conditions.
          </p>
          <button class="action filled" @click=${this._addSchedule}>
            ${oe(Bt)}Add schedule
          </button>
        </div>
      `:j`
      <div class="grid">
        ${vt(this._schedules,t=>t.entry_id,e=>this._renderSchedule(t,e))}
      </div>
    `:this._loadError?Z:j`<div class="empty">Loading schedules…</div>`}_renderSchedule(t,e){const i=e.config??{},n=e.entry_id,s=this._pending[n],r=void 0!==s,o=this._actionErrors[n],a=It(t,i),l=((t,e)=>qt(t,e.last_details))(t,e),d=e.unclosed_zones??[],c=this._evaluations[n];return j`
      <section class="card ${e.enabled?"":"is-disabled"}">
        <header class="card-header">
          <div class="heading">
            <h2>${e.name}</h2>
            <span class="badge ${h=e.status,wt[h]?.tone??"muted"}">${kt(e.status)}</span>
            ${e.paused&&"paused"!==e.status?j`<span class="chip warn">paused</span>`:Z}
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

        ${d.length?j`<div class="banner error card-banner" role="alert">
              ${oe(se)}Could not close
              ${d.map(e=>At(t,e)).join(", ")}. Closing is being
              retried — check the valve.
            </div>`:Z}

        ${e.running?this._renderRunning(t,e):Z}

        <details class="details">
          <summary>${oe(ie)}Details</summary>
          <dl class="rows">
            <dt>Next run</dt>
            <dd>${this._renderNextRun(t,e)}</dd>

            <dt>Rain delay</dt>
            <dd>${this._renderRainDelay(t,e,r)}</dd>

            <dt>Schedule</dt>
            <dd>
              <div>${Tt(t,i)}</div>
              <div class="muted">${((t,e)=>{if("hourly"===e.frequency)return"Every day";if("time"===e.start_mode)return e.start_time?`Starts at ${Dt(t,e.start_time)}`:"Fixed time";const i="sunset"===e.start_mode?"sunset":"sunrise",n=e.sun_offset_minutes??0;return 0===n?`Finishes at ${i}`:n>0?`Finishes ${Ot(n)} before ${i}`:`Finishes ${Ot(-n)} after ${i}`})(t,i)}</div>
            </dd>

            <dt>Zones</dt>
            <dd>${this._renderZones(t,e,r)}</dd>

            <dt>Conditions</dt>
            <dd>
              ${a.length?a.map(t=>j`<div>${t}</div>`):j`<span class="muted">None</span>`}
            </dd>

            <dt>Last run</dt>
            <dd>${this._renderLastRun(t,e)}</dd>

            ${e.last_status_at?j`
                  <dt>Last status</dt>
                  <dd>
                    <div>
                      ${kt(e.status)}
                      <span class="muted">· ${Lt(t,e.last_status_at)}</span>
                    </div>
                    ${l.map(t=>j`<div class="detail ${t.tone??""}">${t.text}</div>`)}
                  </dd>
                `:Z}

            <dt>History</dt>
            <dd>${this._renderHistory(t,e,r)}</dd>
          </dl>
        </details>

        ${c?this._renderEvaluation(t,e,c):Z}

        ${o?j`<div class="banner error card-banner" role="alert">${o}</div>`:Z}

        <footer class="actions">
          ${e.running?j`<button
                class="action danger"
                ?disabled=${r}
                @click=${()=>this._action(e,"stop")}
              >
                ${oe(Kt)}Stop
              </button>`:j`<button
                class="action filled"
                ?disabled=${r}
                @click=${()=>this._openRunDialog(e)}
              >
                ${oe(Ft)}Run now
              </button>`}
          <button
            class="action"
            ?disabled=${r}
            @click=${()=>this._action(e,"skip_next",{skip:!e.skip_next})}
          >
            ${e.skip_next?j`${oe(Jt)}Cancel skip`:j`${oe(Gt)}Skip next`}
          </button>
          <button class="action" ?disabled=${r} @click=${()=>this._evaluate(e)}>
            ${oe(ee)}${"evaluate"===s?"Checking…":"Check now"}
          </button>
          ${i.ai_task_entity?j`
                <button
                  class="action"
                  ?disabled=${r}
                  @click=${()=>this._aiText(e,"generate_report")}
                >
                  ${oe(re)}${"generate_report"===s?"Writing report…":"Weekly report"}
                </button>
                <button
                  class="action"
                  ?disabled=${r}
                  @click=${()=>this._aiText(e,"explain_skips")}
                >
                  ${oe(re)}${"explain_skips"===s?"Explaining…":"Explain skips"}
                </button>
              `:Z}
          <span class="spacer"></span>
          <button
            class="action"
            title="Opens Add schedule; pick Copy an existing schedule"
            @click=${this._addSchedule}
          >
            ${oe(Xt)}Copy
          </button>
          <button class="action" @click=${()=>this._editSchedule(e)}>
            ${oe(Qt)}Edit
          </button>
        </footer>
      </section>
    `;var h}_renderNextRun(t,e){return e.enabled?e.next_run?j`
      ${Lt(t,e.next_run)}
      <span class="muted">(${Ut(e.next_run,this._now)})</span>
      ${!1===e.next_run_scheduled?j`<span class="chip" title="Waters only if a moisture sensor reads below the threshold"
            >moisture check</span
          >`:Z}
      ${e.skip_next?j`<span class="chip warn">next watering skipped</span>`:Z}
      ${e.paused?j`<span class="chip warn">paused</span>`:Z}
    `:j`<span class="muted">Nothing scheduled</span>`:j`<span class="muted">Schedule is off</span>`}_renderRainDelay(t,e,i){const n=e.rain_delay_until;return j`
      ${n?j`<div>
            Until ${Lt(t,n)}
            <span class="muted">(${Ut(n,this._now)})</span>
          </div>`:j`<div class="muted">None</div>`}
      <div class="inline-actions">
        ${de.map(t=>j`<button
            class="mini"
            title=${`Skip scheduled runs for the next ${t} hours`}
            ?disabled=${i}
            @click=${()=>this._action(e,"set_rain_delay",{hours:t})}
          >
            ${t} h
          </button>`)}
        ${n?j`<button
              class="mini"
              ?disabled=${i}
              @click=${()=>this._action(e,"set_rain_delay",{hours:0})}
            >
              Clear
            </button>`:Z}
      </div>
    `}_renderZones(t,e,i){const n=e.config??{},s=n.zones??[];return s.length?j`
      <ul class="zone-list">
        ${s.map(n=>j`<li>
            <button
              class="zone-link"
              title="Open this zone's device"
              @click=${()=>this._openZone(t,n.entity_id)}
            >
              ${At(t,n.entity_id)}
            </button>
            <span class="zone-controls">
              <span class="muted">${n.minutes} min</span>
              <button
                class="mini"
                title="Run only this zone"
                ?disabled=${i||e.running}
                @click=${()=>this._runZone(t,e,n)}
              >
                Run
              </button>
            </span>
          </li>`)}
      </ul>
      ${s.length>1?j`<div class="muted">${(t=>"concurrent"===t.zone_mode?"All zones at once":"One zone at a time")(n)}</div>`:Z}
    `:j`<span class="muted">No zones</span>`}_renderRunning(t,e){let i=e.active_zones??[];return!i.length&&e.current_zone&&(i=[{entity_id:e.current_zone,ends_at:e.current_zone_ends_at}]),j`
      <div class="running-block">
        <div class="running-title">${oe(Yt)}Watering</div>
        ${i.length?i.map(e=>j`<div class="running-zone">
                <span>${At(t,e.entity_id)}</span>
                <span class="countdown">
                  ${e.ends_at?`${((t,e)=>{const i=Math.max(0,Math.round((new Date(t).getTime()-e)/1e3)),n=Math.floor(i/3600),s=Math.floor(i%3600/60),r=i%60,o=t=>String(t).padStart(2,"0");return n>0?`${n}:${o(s)}:${o(r)}`:`${s}:${o(r)}`})(e.ends_at,this._now)} left`:"starting…"}
                </span>
              </div>`):j`<div class="muted">Starting…</div>`}
      </div>
    `}_renderLastRun(t,e){if(!e.last_run_start)return j`<span class="muted">Never</span>`;const i=e.last_run_total_minutes,n=e.zone_results??[];return j`
      <div>
        ${Lt(t,e.last_run_start)}${e.last_run_end?` – ${Pt(t,e.last_run_end)}`:""}
      </div>
      ${null!=i?j`<div class="muted">${Rt(t,i,1)} min total</div>`:Z}
      ${n.length?j`<ul class="zone-list">
            ${n.map(e=>j`<li class=${e.error?"error":""}>
                <span>
                  ${At(t,e.entity_id)}
                  ${e.error?j`<span class="zone-error">${e.error}</span>`:Z}
                </span>
                <span class=${e.error?"":"muted"}>${Rt(t,e.minutes,1)} min</span>
              </li>`)}
          </ul>`:Z}
    `}_renderHistory(t,e,i){const n=this._histories[e.entry_id],s=n??e.history??[];return s.length?j`
      <ul class="history-list">
        ${s.map(e=>{const i="error"===e.status||(e.zones??[]).some(t=>t.error);return j`<li class=${i?"error":""}>
            <span>${((t,e)=>`${Lt(t,e.at)} · ${kt(e.status)}${e.manual?" (manual)":""}`)(t,e)}</span>
            <span class=${i?"":"muted"}>
              ${"run"===e.type?`${Rt(t,e.total_minutes??0,1)} min`:"skip"}
            </span>
          </li>`})}
      </ul>
      ${n?j`<button
            class="mini"
            @click=${()=>this._histories=ue(this._histories,e.entry_id)}
          >
            Show less
          </button>`:s.length>=10?j`<button class="mini" ?disabled=${i} @click=${()=>this._loadHistory(e)}>
              Show more
            </button>`:Z}
    `:j`<span class="muted">No runs or skips yet</span>`}_renderEvaluation(t,e,i){return j`
      <div class="check-block">
        <div class="check-title">
          <span>Check at ${Pt(t,i.at)}</span>
          <button
            class="icon-button small"
            aria-label="Close check result"
            @click=${()=>this._evaluations=ue(this._evaluations,e.entry_id)}
          >
            ${oe(ne)}
          </button>
        </div>
        ${((t,e)=>{const{decision:i}=e,n=[];return i.water?n.push({text:"Conditions allow watering now",tone:"ok"}):i.status?n.push({text:`Would skip: ${kt(i.status)}`,tone:"warn"}):n.push({text:"Would not water: not a schedule day and no sensor is dry",tone:"muted"}),i.retry&&n.push({text:"Would re-check every 2 min until the maximum delay",tone:"info"}),e.scheduled||n.push({text:"Checked as a moisture check day",tone:"muted"}),e.rain_delay_until&&n.push({text:`Rain delay until ${Lt(t,e.rain_delay_until)}: scheduled runs are skipped`,tone:"warn"}),e.paused&&n.push({text:"Paused: scheduled runs do nothing",tone:"warn"}),e.enabled||n.push({text:"Schedule is off",tone:"muted"}),[...n,...qt(t,i.details)]})(t,i).map(t=>j`<div class="detail ${t.tone??""}">${t.text}</div>`)}
      </div>
    `}_renderDialog(){const t=this._dialog;return t?j`
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
    `:Z}_renderRunDialog(){const t=this._runDialog,e=this.hass,i=this._schedules?.find(e=>e.entry_id===t?.entryId);if(!t||!e||!i)return Z;const n=i.config?.zones??[],s=void 0!==this._pending[i.entry_id],r=`Run ${i.name} now`;return j`
      <div class="dialog-backdrop" @click=${this._closeRunDialog}>
        <div
          class="dialog"
          role="dialog"
          aria-modal="true"
          aria-label=${r}
          @click=${t=>t.stopPropagation()}
        >
          <h2>${r}</h2>
          <div class="dialog-text">
            Minutes to water each zone. Start with the schedule's own times to run it as configured.
          </div>
          <ul class="run-zones">
            ${n.map(n=>j`<li>
                <label for=${`run-${n.entity_id}`}>${At(e,n.entity_id)}</label>
                <input
                  id=${`run-${n.entity_id}`}
                  type="number"
                  inputmode="numeric"
                  min="1"
                  max=${ce}
                  step="1"
                  .value=${t.minutes[n.entity_id]??""}
                  @input=${t=>this._setRunMinutes(n.entity_id,t.target.value)}
                  @keydown=${t=>{"Enter"===t.key&&this._startRun(i)}}
                />
                <span class="muted">min</span>
              </li>`)}
          </ul>
          ${t.error?j`<div class="banner error dialog-error" role="alert">${t.error}</div>`:Z}
          <div class="dialog-actions">
            <button class="action" @click=${this._closeRunDialog}>Cancel</button>
            <button class="action filled" ?disabled=${s} @click=${()=>this._startRun(i)}>
              ${oe(Ft)}Start
            </button>
          </div>
        </div>
      </div>
    `}_subscribe(){const t=this.hass;if(!t||!this.isConnected)return;if(this._connection===t.connection&&(this._unsubscribe||Date.now()-this._subscribeFailedAt<3e4))return;this._unsubscribeAll();const e=t.connection;this._connection=e,e.addEventListener("ready",this._handleReconnect);const i=e.subscribeMessage(t=>{this._schedules=t.schedules,this._loadError=void 0},{type:`${le}/subscribe`});this._unsubscribe=i,i.catch(t=>{this._unsubscribe===i&&(this._unsubscribe=void 0,this._subscribeFailedAt=Date.now(),this._loadError=`Could not load schedules: ${he(t)}`)})}_unsubscribeAll(){this._connection?.removeEventListener("ready",this._handleReconnect),this._connection=void 0;const t=this._unsubscribe;this._unsubscribe=void 0,t?.then(t=>t()).catch(()=>{})}async _refresh(){if(this.hass)try{const t=await this.hass.callWS({type:`${le}/schedules`});this._schedules=t.schedules,this._loadError=void 0}catch(t){}}_watchedEntities(){const t=new Set,e=e=>{e&&t.add(e)};for(const t of this._schedules??[]){const i=t.config??{};i.zones?.forEach(t=>e(t.entity_id)),i.moisture_sensors?.forEach(e),i.rain_sensors?.forEach(e),i.weather_entities?.forEach(e),i.occupancy_entities?.forEach(e),e(i.rain_sensor),e(i.weather_entity),e(i.temperature_sensor),e(i.wind_sensor);const n=t.last_details??{};e(n.moisture?.lowest_entity),(n.moisture?.unavailable_entities??[]).forEach(e),(n.occupancy?.occupied??[]).forEach(e),Object.keys(n.rain?.stations??{}).forEach(e),t.unclosed_zones?.forEach(e),t.zone_results?.forEach(t=>e(t.entity_id)),t.active_zones?.forEach(t=>e(t.entity_id))}return[...t]}_tick(){const t=Date.now();(this._schedules?.some(t=>t.running)||t-this._now>=3e4)&&(this._now=t)}async _request(t,e,i={}){const n=this.hass,s=t.entry_id;if(n&&void 0===this._pending[s]){this._pending={...this._pending,[s]:e},this._actionErrors=ue(this._actionErrors,s);try{return await n.callWS({type:`${le}/${e}`,entry_id:s,...i})}catch(t){return void(this._actionErrors={...this._actionErrors,[s]:he(t)})}finally{this._pending=ue(this._pending,s)}}}async _action(t,e,i={}){const n=await this._request(t,e,i);n&&this._schedules&&(this._schedules=this._schedules.map(e=>e.entry_id===t.entry_id?n:e))}async _evaluate(t){const e=await this._request(t,"evaluate");e&&(this._evaluations={...this._evaluations,[t.entry_id]:e})}async _loadHistory(t){const e=await this._request(t,"history",{limit:100});e&&(this._histories={...this._histories,[t.entry_id]:e.history})}async _aiText(t,e){const i=await this._request(t,e);i&&(this._dialog={title:"generate_report"===e?`${t.name}: weekly report`:`${t.name}: skipped runs`,text:i.text})}_runZone(t,e,i){const n=window.prompt(`Run ${At(t,i.entity_id)} for how many minutes?`,String(i.minutes));if(null===n)return;const s=Number(n.trim());!Number.isInteger(s)||s<1||s>ce?this._actionErrors={...this._actionErrors,[e.entry_id]:"Enter whole minutes from 1 to 180."}:this._action(e,"run_zone",{zone:i.entity_id,minutes:s})}async _globalAction(t){const e=this.hass;if(e&&void 0===this._globalPending&&("stop_all"!==t||window.confirm("Stop every active run?"))){this._globalPending=t,this._globalError=void 0;try{const i=await e.callWS({type:`${le}/${t}`});i?.schedules&&(this._schedules=i.schedules)}catch(t){this._globalError=he(t)}finally{this._globalPending=void 0}}}_toggleEnabled(t,e){const i=e.target,n=i.checked;i.checked=t.enabled,this._action(t,"set_enabled",{enabled:n})}_openRunDialog(t){const e=t.config?.zones??[];e.length?(this._actionErrors=ue(this._actionErrors,t.entry_id),this._runDialog={entryId:t.entry_id,minutes:Object.fromEntries(e.map(t=>[t.entity_id,String(t.minutes)]))}):this._action(t,"run_now")}_setRunMinutes(t,e){this._runDialog&&(this._runDialog={...this._runDialog,minutes:{...this._runDialog.minutes,[t]:e},error:void 0})}_startRun(t){const e=this._runDialog;if(!e||void 0!==this._pending[t.entry_id])return;const i={};for(const n of t.config?.zones??[]){const t=(e.minutes[n.entity_id]??"").trim(),s=Number(t);if(!t||!Number.isInteger(s)||s<1||s>ce)return void(this._runDialog={...e,error:"Enter whole minutes from 1 to 180 for every zone."});s!==n.minutes&&(i[n.entity_id]=s)}this._runDialog=void 0,this._action(t,"run_now",Object.keys(i).length?{zone_minutes:i}:{})}_toggleMenu(){this.dispatchEvent(new CustomEvent("hass-toggle-menu",{bubbles:!0,composed:!0}))}_addSchedule(){pe(`/_my_redirect/config_flow_start?domain=${le}`)}_editSchedule(t){pe(`/config/integrations/integration/${le}#config_entry=${t.entry_id}`)}_openZone(t,e){const i=t.entities?.[e]?.device_id;i?pe(`/config/devices/device/${i}`):this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:e},bubbles:!0,composed:!0}))}};_e.styles=ae,t([ct({attribute:!1})],_e.prototype,"hass",void 0),t([ct({type:Boolean,reflect:!0})],_e.prototype,"narrow",void 0),t([ct({attribute:!1})],_e.prototype,"route",void 0),t([ct({attribute:!1})],_e.prototype,"panel",void 0),t([ht()],_e.prototype,"_schedules",void 0),t([ht()],_e.prototype,"_loadError",void 0),t([ht()],_e.prototype,"_pending",void 0),t([ht()],_e.prototype,"_actionErrors",void 0),t([ht()],_e.prototype,"_evaluations",void 0),t([ht()],_e.prototype,"_histories",void 0),t([ht()],_e.prototype,"_globalPending",void 0),t([ht()],_e.prototype,"_globalError",void 0),t([ht()],_e.prototype,"_dialog",void 0),t([ht()],_e.prototype,"_runDialog",void 0),t([ht()],_e.prototype,"_now",void 0),_e=t([(t=>(e,i)=>{void 0!==i?i.addInitializer(()=>{customElements.define(t,e)}):customElements.define(t,e)})("irrigation-manager-panel")],_e);export{_e as IrrigationManagerPanel};
