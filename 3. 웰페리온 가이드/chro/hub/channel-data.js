/* channel-data.js — 채널 배포 센터(A-5, 2026-07-19) 데이터·생성기.
 * index.html의 "채널 배포" 탭이 사용. 로컬 job-post-formatter.js(.claude/tools) 템플릿을
 * 브라우저용으로 이식 — 로직 동일, Node fs/path 의존만 제거.
 * 범위: 로컬 텍스트/HTML 생성만. 외부 플랫폼 접속·자동 게시 없음(복사·다운로드용 준비 도구).
 * 데이터 출처: .claude/tools/job-post-source.*.json(기존 3건) + operations.html·db:hire row8·
 *   drafts/카페게시_재료_운영부_20260719.txt(신규 1건, 오늘 세션 실측) — 전부 실공고 내용, 창작 없음.
 */
(function(global){
  "use strict";

  function esc(s){
    return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }
  // 비BMP(이모지 등) 제거 — 잡코리아/알바몬 에디터 "?" 깨짐 방지
  function stripNonBMP(s){
    var removed=0;
    var out=String(s).replace(/[\u{10000}-\u{10FFFF}]/gu,function(){removed++;return "";});
    return {text:out, removed:removed};
  }
  function titleRank(d){ return d.title.indexOf(d.rank)>=0 ? d.title : (d.title+" ("+d.rank+")"); }

  /* ============ 포지션 소스 데이터 (4건 — 현재 공고중과 매칭) ============ */
  var SOURCES = {
    "sauna-jooim": {
      id:"sauna-jooim", generatedLabel:"20260718",
      title:"남자사우나 주임", titleLong:"남자사우나 주임 채용",
      dept:"지원부", employmentType:"정규직", rank:"주임",
      location:"서울 한남동", locationDetail:"서울 용산구 한남동 (이태원·한남 인근)",
      heroSub:"프리미엄 사우나·스파를 책임질 남자사우나 주임을 모십니다.",
      heroBadge:"남자사우나·스파 관리 · 회원 응대 · 주임급",
      communityCafes:["sportsdream"],
      salary:{label:"월 급여",unit:"/ 월",amount:"243만원",monthly:"월 243만원",
        note:"수습기간 100% 지급 (감액 없음) · 주임 직급 · 유관업종 경력자 우대"},
      perkCards:[
        {icon:"▲",title:"명확한 진급 체계",desc:"주임 → 반장 → 팀장까지, 성과에 따라 공정하게 올라가는 3단계 진급 시스템"},
        {icon:"●",title:"점심식사 50% 지원",desc:"지정 한식 뷔페 이용 시 식대의 절반을 회사가 지원합니다"},
        {icon:"★",title:"연말 성과 포상",desc:"센터 수익에 따른 정직원 연말 포상 (1년 이상 근속자 대상)"}
      ],
      perkWide:{icon:"◆",title:"AI 업무 서포트 (전 직원 제공)",
        desc:"반복 업무는 AI가 돕습니다. 누구나 더 빠르고 똑똑하게 일할 수 있는 환경을 제공합니다. · 유니폼 제공(근무 유니폼 회사 지급)"},
      ladder:[{label:"① 주임",desc:"연차가 아닌 성과로 평가"},{label:"② 반장",desc:"진급 2단계"},{label:"③ 팀장",desc:"진급 3단계"}],
      tags:["서비스 마인드 및 태도","위생 · 시설 관리","고객 응대 · 커뮤니케이션","연 / 월차 제도","퇴직금 제도","직원할인(카페)","유니폼 제공 등"],
      duties:["남자사우나·스파 시설 위생·청결 및 온도/습도 관리","어메니티·비품·린넨 관리 및 재고 점검",
        "남성 회원 응대 및 시설 이용 안내","사우나 시설 안전 점검 및 이상 사항 보고","사우나 파트 운영 관리 (주임)"],
      requirements:["학력 : 무관","경력 : 무관 (신입 지원 가능)","지원 서류 : 이력서(사진 포함) · 자기소개서"],
      preferred:["사우나·스파·호텔 등 유관업무 경험자","시설·위생 관리 경험자 · 즉시출근 가능자","서비스 마인드 보유"],
      shift:[{label:"평일 (월~금)",detail:"근무 14:00 ~ 22:40"},
        {label:"주말 (토·일)",detail:"오픈 07:40~15:00 / 마감 12:50~20:10 · 교대 · 휴게 1시간 포함"}],
      off:"월 6회 휴무 (6회 + 공휴일 수)",
      benefits:["명확한 진급 체계 — 주임 → 반장 → 팀장 3단계, 연차가 아닌 성과 기반 진급","점심식사 50% 지원 (지정 한식 뷔페)",
        "연말 성과 포상 (1년 이상 근속자 대상)","AI 업무 서포트 — 반복 업무는 AI가 돕는 근무 환경 (전 직원 제공)",
        "유니폼 제공 · 연/월차 제도 · 퇴직금 제도 · 직원할인(카페)"],
      hashtags:["웰페리온","한남동채용","사우나채용","스파채용","정규직채용","한남동일자리","프리미엄스포츠클럽","사우나주임","이태원채용","위생관리","서비스직","웰페리온채용"]
    },
    "golf-pro": {
      id:"golf-pro", generatedLabel:"20260718",
      title:"오전 골프 프로", titleLong:"오전 골프 프로 채용",
      dept:"강습부", employmentType:"파트너(위탁)", rank:"어소시에이트 프로",
      location:"서울 한남동", locationDetail:"서울 용산구 한남동 (이태원·한남 인근) · 웰페리온 101동 B1~B2",
      heroSub:"강습부 — 회원의 아침을 여는 골프 레슨, 함께 성장할 프로님을 모십니다.",
      heroBadge:"골프 프로 (어소시에이트 프로 · 1단계) · 파트너(위탁) · 오전 업장 관리",
      communityCafes:["sportsdream"],
      salary:{label:"보상 (PARTNER)",unit:"수업료율",amount:"40% → 55%",
        monthly:"수업료율 40%→55% + 정착지원금 월 100~130만원",
        note:"정착지원금 기간(3개월) 40% 정액 → 종료 후 55%(기본 프로) · 일반 월 100만원 / 시니어 월 130만원"},
      perkCards:[
        {icon:"●",title:"정착지원금 (입사 3개월)",desc:"계약 시작 후 3개월간 일반 月 100만원 / 시니어 月 130만원 지원으로 안정적인 정착을 돕습니다."},
        {icon:"▲",title:"파트너 등급제",desc:"어소시에이트 → 기본 → 마스터 → 시니어 → 팀리더. 성과·전문성에 따라 수업료율이 단계적으로 오릅니다."},
        {icon:"★",title:"프리미엄 골프 인프라",desc:"한남동 프리미엄 멤버십 회원과 정돈된 골프 레슨 환경에서 일합니다."}
      ],
      perkWide:{icon:"◆",title:"AI 업무 서포트 (전 강사 제공)",
        desc:"스케줄·페이롤 등 반복 업무는 AI가 돕습니다. 레슨에 더 집중할 수 있는 환경을 제공합니다. · 강습 유니폼 제공"},
      ladder:[{label:"① 어소시에이트 프로",desc:"40% (정착) / 55%"},{label:"② 기본 프로",desc:"55%"},
        {label:"③ 마스터 프로",desc:"58% (석·박사·투어프로)"},{label:"④ 시니어 프로",desc:"58% + 인센티브"},{label:"⑤ 팀리더",desc:"60% + 인센티브"}],
      tags:["레슨 전문성","서비스마인드","안전관리","성실성","성장지향성"],
      duties:["회원 골프 레슨(개인·그룹) 진행 및 강습 콘텐츠 준비","스윙·자세 지도, 회원 컨디션 체크 및 안전관리(warm up / cool down)",
        "오전 업장 관리 — 시설·장비 점검, 강습 공간 정리정돈","강습 기록 관리 및 팀 관리자·운영부 공유","회원 응대 및 재등록 관리"],
      requirements:["골프프로 (KPGA · KLPGA) 소속 프로","골프 레슨 지도 가능자","경력 : 무관 (1단계 어소시에이트부터 성장)","회원 안전·서비스 마인드 · 단정한 용모 · 유니폼 착용"],
      preferred:["골프 레슨 · 지도 경력자","인근 거주자 · 즉시 활동 가능자","CPR · AED 등 안전교육 이수자"],
      shift:[{label:"업장 관리 (평일)",detail:"06:00 ~ 14:00 (8h)"},{label:"업장 관리 (주말)",detail:"08:00 ~ 14:00 (6h) · 휴게 1시간 포함"}],
      off:"주 5일 · 월 6일 미운영 (정착지원금 종료 후 월 8일)",
      benefits:["정착지원금 (입사 3개월) — 일반 월 100만원 / 시니어 월 130만원 지원으로 안정적인 정착",
        "파트너 등급제 — 어소시에이트 → 기본 → 마스터 → 시니어 → 팀리더, 성과·전문성에 따라 수업료율 단계 상승",
        "프리미엄 골프 인프라 — 한남동 프리미엄 멤버십 회원과 정돈된 레슨 환경",
        "AI 업무 서포트 — 스케줄·페이롤 등 반복 업무는 AI가 돕는 환경 (전 강사 제공)","강습 유니폼 제공"],
      hashtags:["웰페리온","한남동채용","골프프로채용","골프강사","KPGA","KLPGA","오전골프프로","골프레슨","강습부","프리미엄스포츠클럽","골프프로모집","이태원채용"]
    },
    "parking": {
      id:"parking", generatedLabel:"20260719",
      title:"주차관리자 · 발렛파킹 (시설부)", titleLong:"주차관리자 · 발렛파킹 채용",
      dept:"시설부", employmentType:"정규직 (수습 3개월)", rank:"사원~대리급",
      location:"서울 한남동", locationDetail:"웰페리온 101동 B1~B2 (경의중앙선 한남역 도보 7분)",
      heroSub:"시설부 — 프리미엄 멤버십 스포츠 클럽의 첫인상을 책임질 분을 모십니다.",
      heroBadge:"주차관리·발렛 기사 · 정규직(수습 3개월) · 모집 1명",
      communityCafes:[],
      salary:{label:"월 급여",unit:"/ 월",amount:"270만원",monthly:"월 270만원",
        note:"연 3,240만원 · 정규직(수습 3개월) · 직급 사원~대리급"},
      perkCards:[
        {icon:"▲",title:"점심식사 50% 지원",desc:"지정 한식 뷔페 이용 시 식대의 절반을 회사가 지원합니다"},
        {icon:"●",title:"유니폼 제공",desc:"깔끔한 근무 유니폼을 회사에서 지급합니다"},
        {icon:"★",title:"연말 성과 포상",desc:"센터 수익에 따른 연말 포상 (1년 이상 근속자 대상)"}
      ],
      perkWide:{icon:"◆",title:"AI 업무 서포트 (전 직원 제공)",
        desc:"반복 업무는 AI가 돕습니다. 누구나 더 빠르고 똑똑하게 일할 수 있는 환경을 제공합니다. · 직원할인(카페) · 4대보험 적용"},
      ladder:[],
      tags:["서비스 마인드 및 태도","LPR 시스템 운영","고객 응대 · 민원 처리","연 / 월차 제도","퇴직금 제도","직원할인(카페)","유니폼 제공 등"],
      duties:["웰페리온 1층 주차장 차량 입출차 관리","LPR(차량번호 인식) 시스템 모니터링 및 오류 대응","발렛 서비스 지원 (회원 차량 이동·인도)",
        "주차 요금 정산 및 민원 응대","주차장 시설 점검 및 안전 관리","VIP 회원 맞춤형 주차 안내 서비스"],
      requirements:["운전면허 : 1종 보통","경력·학력 : 무관","지원 서류 : 이력서(사진 포함) · 자기소개서"],
      preferred:["인근 거주자","유관업무 경험자 (인턴·아르바이트 포함)","즉시 출근 가능자","장기 근무 가능자"],
      shift:[{label:"근무일",detail:"평일 09:30 ~ 18:30"},{label:"휴무",detail:"월 6회 휴무 (공휴일에 따라 추가) · 격주휴무"}],
      off:"월 6회 휴무 (공휴일에 따라 추가) · 격주휴무",
      benefits:["4대보험 (국민연금·고용·산재·건강) · 퇴직금 제도","격주휴무 · 연차/월차 제도","직원할인(카페) · 유니폼 제공",
        "AI 업무 서포트 — 반복 업무는 AI가 돕는 근무 환경 (전 직원 제공)"],
      hashtags:["웰페리온","한남동채용","주차관리채용","발렛파킹채용","정규직채용","한남동일자리","프리미엄스포츠클럽","시설부채용","이태원채용","주차관리자","발렛기사","웰페리온채용"]
    },
    "operations-pm": {
      id:"operations-pm", generatedLabel:"20260719",
      title:"운영부 사원 (오후)", titleLong:"운영부 직원 신규 채용 (오후 근무)",
      dept:"운영부", employmentType:"정규직 (수습 3개월)", rank:"사원",
      location:"서울 한남동", locationDetail:"서울 용산구 한남동 웰페리온",
      heroSub:"웰페리온과 함께 성장할 새로운 팀원을 모십니다.",
      heroBadge:"회원 상담 · 운영 지원 · 오후 근무 1명",
      communityCafes:["sportsdream"],
      salary:{label:"연봉",unit:"/ 년",amount:"3,240만원",monthly:"연 3,240만원",
        note:"수습 3개월 월 270만원 지급 · 정규직 전환 후 사원 직급 시작 · 영어 회화 가능자 등 우대 시 급여 추가 조정"},
      perkCards:[
        {icon:"▲",title:"명확한 진급 체계",desc:"사원 → 부장까지, 성과에 따라 공정하게 올라가는 6단계 진급 시스템"},
        {icon:"●",title:"점심식사 50% 지원",desc:"지정 한식 뷔페 이용 시 식대의 절반을 회사가 지원합니다"},
        {icon:"★",title:"연말 성과 포상",desc:"센터 수익에 따른 정직원 연말 포상 (1년 이상 근속자 대상)"}
      ],
      perkWide:{icon:"◆",title:"AI 업무 서포트 (전 직원 제공)",
        desc:"반복 업무는 AI가 돕습니다. 누구나 더 빠르고 똑똑하게 일할 수 있는 환경을 제공합니다. · 근무 유니폼 제공"},
      ladder:[{label:"① 사원",desc:"연차가 아닌 성과로 평가"},{label:"② 주임",desc:"진급 2단계"},{label:"③ 대리",desc:"진급 3단계"},
        {label:"④ 과장",desc:"진급 4단계"},{label:"⑤ 차장",desc:"진급 5단계"},{label:"⑥ 부장",desc:"진급 6단계"}],
      tags:["Excel","서비스 마인드 및 태도","고객 응대 · 커뮤니케이션","연 / 월차 제도","퇴직금 제도","직원할인(카페)","유니폼 제공 등"],
      duties:["리셉션(안내데스크) 포지션 근무","문의(회원·결제·전화) 응대"],
      requirements:["학력 : 고졸 이상","경력 : 신입","지원 서류 : 이력서(사진 포함) · 자기소개서"],
      preferred:["외국어(영어) 회화 가능자 (급여 추가조정)","유관업무 경험자 · 즉시출근 가능자","서비스 마인드 보유"],
      shift:[{label:"평일",detail:"13:40 ~ 22:40 (휴게 1시간)"},{label:"주말",detail:"13:10 ~ 20:10 (휴게 1시간)"}],
      off:"월 6회 휴무 (6회 + 공휴일 수) · 협의 후 진행",
      benefits:["명확한 진급 체계 — 사원 → 부장까지 6단계, 성과 기반 진급","점심식사 50% 지원 (지정 한식 뷔페)",
        "연말 성과 포상 (1년 이상 근속자 대상)","AI 업무 서포트 — 반복 업무는 AI가 돕는 근무 환경 (전 직원 제공)",
        "유니폼 제공 · 연/월차 제도 · 퇴직금 제도 · 직원할인(카페)"],
      hashtags:["웰페리온","한남동채용","운영부채용","리셉션채용","정규직채용","한남동일자리","프리미엄스포츠클럽","오후근무","이태원채용","고객응대","서비스직","웰페리온채용"]
    }
  };

  // 전 포지션 공통(회사 소개) — 4개 소스 JSON 전부 동일했던 값을 1곳으로 통합
  var COMPANY = {
    name:"WELLPERION 웰페리온", oneLiner:"서울 한남동의 프리미엄 멤버십 스포츠 클럽",
    about:"웰페리온은 단순한 운동 시설이 아닙니다. 서울 한남동에 자리한, 하루 루틴에 자연스럽게 녹아들어 건강의 기준을 세우는 프리미엄 멤버십 스포츠 클럽입니다. 스포츠·스파·커뮤니티·공간이 하나로 통합된 라이프스타일 인프라를 9년간 가꿔왔습니다.",
    stats:[{k:"한남동",v:"Seoul · 프리미엄 입지"},{k:"9년+",v:"검증된 운영"},{k:"3,000평",v:"통합 라이프스타일 공간"},{k:"4 in 1",v:"스포츠 · 스파 · 커뮤니티 · 카페"}],
    slogan:"최고의 공간은 결국, 사람이 완성합니다"
  };
  var CONTACT = {email:"cao@wellperion.com", phone:"02-6261-1202", manager:"나우열 매니저",
    howto:"이력서(사진 포함)와 자기소개서를 이메일로 보내주시면 확인 후 연락드립니다."};

  var CAFE_NAME = {sportsdream:"스포드림 카페", hohoyoga:"호호요가 카페"};
  var CAFE_BOARD = {sportsdream:"스포츠센터(종합시설)", hohoyoga:"강사 구인 게시판"};

  function urlsFor(d){
    var slugMap={"sauna-jooim":"sauna.html","golf-pro":"golfpro.html","parking":"parking.html","operations-pm":"operations.html"};
    var page=slugMap[d.id]||"index.html";
    return {
      recruitPage:"https://wellperion-cao.github.io/wellperion-automation/chro/recruiting/"+page,
      recruitIndex:"https://wellperion-cao.github.io/wellperion-automation/chro/recruiting/",
      valuesDiagram:"https://wellperion-cao.github.io/wellperion-automation/chro/recruiting/assets/values-diagram.png"
    };
  }

  // 렌더용으로 회사·연락처·URL을 채운 완성 데이터 반환
  function fullData(key){
    var base=SOURCES[key]; if(!base) return null;
    var d={}; for(var k in base){ d[k]=base[k]; }
    d.company=COMPANY; d.contact=CONTACT; d.urls=urlsFor(d);
    return d;
  }

  /* ============ 포지션 매칭 (db:hire 포지션명·부서 → 소스 키) ============ */
  function matchSource(posName, dept){
    var n=String(posName||""), dp=String(dept||"");
    if(/사우나/.test(n)) return "sauna-jooim";
    if(/골프.*프로|골프프로/.test(n)) return "golf-pro";
    if(/주차|발렛/.test(n) && dp.indexOf("시설")>=0) return "parking";
    if(/운영부|리셉션/.test(n) && (dp.indexOf("운영")>=0)) return "operations-pm";
    return null;
  }

  /* ============ A. 잡코리아 — 에디터 호환 리치 HTML ============ */
  function jobkoreaHtml(d){
    var stats=d.company.stats.map(function(s){
      return '    <div class="card m-stat"><b>'+esc(s.k)+'</b><span>'+esc(s.v)+'</span></div>';
    }).join("\n");
    var li=function(x){ return '      <div class="li"><span class="dot">·</span><span>'+esc(x)+'</span></div>'; };
    var duties=d.duties.map(li).join("\n");
    var req=d.requirements.map(li).join("\n");
    var pref=d.preferred.map(li).join("\n");
    var perks=d.perkCards.map(function(p){
      return '    <div class="card m-perk">\n      <div class="ic">'+esc(p.icon)+'</div>\n      <h3>'+esc(p.title)+'</h3>\n      <p>'+esc(p.desc)+'</p>\n    </div>';
    }).join("\n");
    var hasLadder=Array.isArray(d.ladder)&&d.ladder.length>0;
    var ladder=hasLadder ? d.ladder.map(function(s){
      return '        <div class="step"><b>'+esc(s.label)+'</b><span>'+esc(s.desc)+'</span></div>';
    }).join("\n") : "";
    var ladderCard=hasLadder ?
      '    <div class="card m-ladder">\n      <div class="m-title">성과 기반 진급 시스템</div>\n      <div class="ladder-row">\n'+ladder+'\n      </div>\n    </div>\n' : "";
    var tags=d.tags.map(function(t){return '        <span class="chip">'+esc(t)+'</span>';}).join("\n");
    var shiftWeekday=d.shift[0], shiftWeekend=d.shift[1];

    var html='<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="UTF-8">\n'+
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'+
    '<title>웰페리온 채용공고 · '+esc(d.titleLong)+'</title>\n<style>\n'+
    '  :root{\n    --navy:#0b1f3a; --navy-2:#173a5e; --accent:#3f6fa0; --accent-soft:#e8f0f7;\n'+
    '    --gold:#2f76b4; --ink:#141e2c; --muted:#5c6b7e; --line:#dbe5ef; --bg:#eef3f8; --card:#ffffff;\n  }\n'+
    '  *{box-sizing:border-box;margin:0;padding:0;}\n'+
    '  body{font-family:"Pretendard","Apple SD Gothic Neo","Malgun Gothic","맑은 고딕",sans-serif;\n'+
    '    background:var(--bg);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased;}\n'+
    '  .wrap{max-width:1040px;margin:0 auto;padding:28px 20px 60px;}\n'+
    '  .topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:10px;}\n'+
    '  .topbar .brand{font-size:13px;font-weight:800;letter-spacing:3px;color:var(--navy);}\n'+
    '  .status{font-size:11.5px;font-weight:700;padding:5px 12px;border-radius:999px;border:1px solid transparent;}\n'+
    '  .status.open{color:#2f7d4f;background:#e6f4ea;border-color:#cfe9d7;}\n'+
    '  .bento{display:grid;grid-template-columns:repeat(12,1fr);gap:14px;}\n'+
    '  .card{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:22px;box-shadow:0 4px 16px rgba(11,31,58,.05);}\n'+
    '  .m-hero{grid-column:span 8;background:linear-gradient(135deg,var(--navy),var(--navy-2));color:#fff;border:none;\n'+
    '    display:flex;flex-direction:column;justify-content:center;position:relative;overflow:hidden;min-height:200px;}\n'+
    '  .m-hero::after{content:"";position:absolute;right:-40px;top:-40px;width:200px;height:200px;border-radius:50%;background:rgba(63,111,160,.25);}\n'+
    '  .m-hero .eyebrow{font-size:12px;letter-spacing:3px;color:#a9c9e8;font-weight:700;text-transform:uppercase;position:relative;}\n'+
    '  .m-hero h1{font-size:32px;font-weight:800;margin-top:10px;letter-spacing:-.8px;position:relative;}\n'+
    '  .m-hero .sub{font-size:14.5px;color:#c9daea;margin-top:8px;max-width:440px;position:relative;}\n'+
    '  .m-hero .badge{margin-top:16px;display:inline-block;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);\n'+
    '    padding:6px 14px;border-radius:999px;font-size:12.5px;font-weight:600;position:relative;width:fit-content;}\n'+
    '  .m-salary{grid-column:span 4;background:linear-gradient(160deg,#173a5e,#0b1f3a);color:#fff;border:none;\n'+
    '    display:flex;flex-direction:column;justify-content:center;}\n'+
    '  .m-salary .lab{font-size:11.5px;letter-spacing:2px;color:#a9c9e8;font-weight:700;text-transform:uppercase;}\n'+
    '  .m-salary .amt{font-size:26px;font-weight:800;margin-top:8px;letter-spacing:-.5px;}\n'+
    '  .m-salary .amt small{font-size:13px;font-weight:500;color:#c9daea;}\n'+
    '  .m-salary .note{margin-top:10px;font-size:12px;color:#c9daea;line-height:1.6;}\n'+
    '  .m-about{grid-column:span 12;}\n'+
    '  .m-about p{font-size:14px;color:var(--muted);line-height:1.85;word-break:keep-all;max-width:760px;}\n'+
    '  .m-stat{grid-column:span 3;text-align:center;}\n'+
    '  .m-stat b{display:block;font-size:18px;font-weight:800;color:var(--navy);}\n'+
    '  .m-stat span{display:block;font-size:11px;color:var(--muted);margin-top:6px;line-height:1.5;word-break:keep-all;}\n'+
    '  .m-title{font-size:11px;letter-spacing:2px;color:var(--accent);font-weight:800;text-transform:uppercase;margin-bottom:12px;}\n'+
    '  .m-values{grid-column:span 12;text-align:center;}\n'+
    '  .m-values .t-kicker{font-size:13px;letter-spacing:3px;color:var(--accent);font-weight:800;}\n'+
    '  .m-values h2{font-size:23px;font-weight:800;margin:6px 0 4px;letter-spacing:-.5px;}\n'+
    '  .m-values .t-sub{font-size:13.5px;color:var(--muted);margin-bottom:10px;}\n'+
    '  .values-diagram{width:100%;max-width:330px;height:auto;display:block;margin:4px auto 0;}\n'+
    '  .quote{margin-top:16px;border-radius:16px;padding:24px 22px;background:linear-gradient(120deg,#0b1f3a,#173a5e);color:#fff;position:relative;overflow:hidden;text-align:center;}\n'+
    '  .quote .s-line{font-size:18px;font-weight:800;line-height:1.5;letter-spacing:-.4px;position:relative;}\n'+
    '  .quote .s-line b{color:var(--gold);}\n'+
    '  .m-ladder{grid-column:span 12;}\n'+
    '  .ladder-row{display:flex;flex-wrap:wrap;gap:10px;margin-top:4px;}\n'+
    '  .ladder-row .step{flex:1 1 130px;background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:12px 14px;}\n'+
    '  .ladder-row .step b{display:block;font-size:13.5px;color:var(--navy);}\n'+
    '  .ladder-row .step span{font-size:12px;color:var(--muted);}\n'+
    '  .m-perk{grid-column:span 4;}\n'+
    '  .m-perk .ic{width:42px;height:42px;border-radius:12px;background:var(--accent-soft);display:flex;align-items:center;justify-content:center;margin-bottom:12px;font-size:18px;color:var(--accent);font-weight:800;}\n'+
    '  .m-perk h3{font-size:15px;font-weight:800;margin-bottom:5px;}\n'+
    '  .m-perk p{font-size:12.5px;color:var(--muted);line-height:1.55;}\n'+
    '  .m-perk-wide{grid-column:span 12;background:linear-gradient(120deg,var(--navy),var(--navy-2));color:#fff;border:none;\n'+
    '    display:flex;align-items:center;gap:16px;flex-wrap:wrap;}\n'+
    '  .m-perk-wide .ic{width:46px;height:46px;border-radius:12px;background:rgba(255,255,255,.14);display:flex;align-items:center;justify-content:center;flex:0 0 auto;font-size:20px;color:#fff;font-weight:800;}\n'+
    '  .m-perk-wide h3{font-size:15.5px;font-weight:800;}\n'+
    '  .m-perk-wide p{font-size:12.5px;color:#c9daea;margin-top:3px;}\n'+
    '  .m-list{grid-column:span 6;}\n'+
    '  .li{display:flex;gap:8px;font-size:13.5px;color:var(--ink);padding:5px 0;}\n'+
    '  .li .dot{color:var(--accent);font-weight:800;flex:0 0 auto;}\n'+
    '  .li .muted{color:var(--muted);}\n'+
    '  .m-shift{grid-column:span 4;}\n'+
    '  .m-shift .sh-top{font-weight:800;font-size:13px;color:var(--navy);margin-bottom:8px;}\n'+
    '  .m-shift .row{font-size:12.5px;padding:3px 0;color:var(--ink);}\n'+
    '  .m-shift .row b{color:var(--navy);}\n'+
    '  .m-shift .off{margin-top:8px;font-size:11px;color:var(--accent);font-weight:700;background:var(--accent-soft);border-radius:8px;padding:6px 9px;line-height:1.5;}\n'+
    '  .m-tags{grid-column:span 12;}\n'+
    '  .chips{display:flex;flex-wrap:wrap;gap:8px;}\n'+
    '  .chip{background:var(--accent-soft);color:var(--navy);font-weight:700;font-size:12.5px;padding:6px 13px;border-radius:999px;border:1px solid var(--line);}\n'+
    '  .m-contact{grid-column:span 12;background:linear-gradient(135deg,var(--navy),var(--navy-2));color:#fff;border:none;}\n'+
    '  .m-contact .m-title{color:#a9c9e8;}\n'+
    '  .contact-grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:14px;}\n'+
    '  .cbox{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);border-radius:16px;padding:18px 20px;}\n'+
    '  .cbox .clab{font-size:11.5px;font-weight:700;color:#a9c9e8;letter-spacing:.3px;margin-bottom:8px;}\n'+
    '  .cbox .cval{font-size:21px;font-weight:800;color:#fff;letter-spacing:-.2px;word-break:break-all;}\n'+
    '  .cbox .csub{margin-top:4px;font-size:12px;color:#c9daea;}\n'+
    '  .m-contact .hint{margin-top:14px;font-size:12px;color:#c9daea;text-align:center;}\n'+
    '  .m-foot{grid-column:span 12;text-align:center;font-size:12px;color:var(--muted);background:transparent;border:none;box-shadow:none;padding-top:6px;}\n'+
    '  .m-foot b{color:var(--navy);}\n'+
    '  @media(max-width:820px){\n    .m-hero{grid-column:span 12;} .m-salary{grid-column:span 12;}\n'+
    '    .m-stat{grid-column:span 6;} .m-perk{grid-column:span 6;}\n'+
    '    .m-list{grid-column:span 12;} .m-shift{grid-column:span 6;}\n'+
    '    .contact-grid2{grid-template-columns:1fr;}\n  }\n'+
    '  @media(max-width:620px){ .m-perk{grid-column:span 12;} .m-shift{grid-column:span 12;} }\n'+
    '</style>\n</head>\n<body data-jobkey="'+esc(d.title)+'">\n<div class="wrap">\n'+
    '  <div class="topbar">\n    <div class="brand">WELLPERION</div>\n'+
    '    <div class="status open">● 채용중 · '+esc(d.dept)+'</div>\n  </div>\n'+
    '  <div class="bento">\n    <div class="card m-hero">\n      <span class="eyebrow">Now Hiring</span>\n'+
    '      <h1>'+esc(d.titleLong)+'</h1>\n      <div class="sub">'+esc(d.heroSub)+'</div>\n'+
    '      <div class="badge">'+esc(d.heroBadge)+'</div>\n    </div>\n'+
    '    <div class="card m-salary">\n      <div class="lab">'+esc(d.salary.label||"월 급여")+'</div>\n'+
    '      <div class="amt">'+esc(d.salary.amount)+' <small>'+esc(d.salary.unit||"/ 월")+'</small></div>\n'+
    '      <div class="note">'+esc(d.salary.note)+'</div>\n    </div>\n'+
    '    <div class="card m-about">\n      <div class="m-title">ABOUT WELLPERION</div>\n      <p>'+esc(d.company.about)+'</p>\n    </div>\n'+
    stats+'\n'+
    '    <div class="card m-values">\n      <div class="t-kicker">WHO WE LOOK FOR</div>\n      <h2>웰페리온 인재상</h2>\n'+
    '      <div class="t-sub">네 가지 핵심 역량이 만나는 지점에 웰페리온의 인재가 있습니다</div>\n'+
    '      <img class="values-diagram" src="'+esc(d.urls.valuesDiagram)+'" alt="웰페리온 인재상 도식">\n'+
    '      <div class="quote"><div class="s-line">'+esc(d.company.slogan)+'</div></div>\n    </div>\n'+
    perks+'\n'+
    '    <div class="card m-perk-wide">\n      <div class="ic">'+esc(d.perkWide.icon)+'</div>\n      <div>\n'+
    '        <h3>'+esc(d.perkWide.title)+'</h3>\n        <p>'+esc(d.perkWide.desc)+'</p>\n      </div>\n    </div>\n'+
    ladderCard+
    '    <div class="card m-list">\n      <div class="m-title">담당 업무</div>\n'+duties+'\n    </div>\n'+
    '    <div class="card m-list">\n      <div class="m-title">자격 요건 · 지원 서류</div>\n'+req+'\n    </div>\n'+
    '    <div class="card m-shift">\n      <div class="sh-top">'+esc(shiftWeekday.label)+'</div>\n'+
    '      <div class="row">'+esc(shiftWeekday.detail)+'</div>\n      <div class="off">'+esc(d.off)+'</div>\n    </div>\n'+
    '    <div class="card m-shift">\n      <div class="sh-top">'+esc(shiftWeekend.label)+'</div>\n'+
    '      <div class="row">'+esc(shiftWeekend.detail)+'</div>\n      <div class="off">'+esc(d.off)+'</div>\n    </div>\n'+
    '    <div class="card m-shift">\n      <div class="sh-top">우대 사항</div>\n'+pref+'\n    </div>\n'+
    '    <div class="card m-tags">\n      <div class="m-title">필요 스킬 · 직원 복지</div>\n      <div class="chips">\n'+tags+'\n      </div>\n    </div>\n'+
    '    <div class="card m-contact">\n      <div class="m-title">지원 및 문의</div>\n      <div class="contact-grid2">\n'+
    '        <div class="cbox">\n          <div class="clab">이메일</div>\n          <div class="cval">'+esc(d.contact.email)+'</div>\n        </div>\n'+
    '        <div class="cbox">\n          <div class="clab">문의 전화</div>\n          <div class="cval">'+esc(d.contact.phone)+'</div>\n'+
    '          <div class="csub">'+esc(d.contact.manager)+'</div>\n        </div>\n      </div>\n'+
    '      <div class="hint">'+esc(d.contact.howto)+'</div>\n    </div>\n'+
    '    <div class="card m-foot">\n      <b>WELLPERION</b> · '+esc(d.titleLong)+' 공고 · 함께 성장할 분들의 많은 지원 바랍니다.\n    </div>\n'+
    '  </div>\n</div>\n</body>\n</html>';
    return stripNonBMP(html);
  }

  /* ============ B. 알바몬 — 보수적 안전판(인라인 스타일) ============ */
  function albamonHtml(d){
    var li=function(x){ return '<li style="margin:4px 0;">'+esc(x)+'</li>'; };
    var duties=d.duties.map(li).join("\n      ");
    var req=d.requirements.map(li).join("\n      ");
    var pref=d.preferred.map(li).join("\n      ");
    var ben=d.benefits.map(li).join("\n      ");
    var shift=d.shift.map(function(s){ return '<li style="margin:4px 0;"><b>'+esc(s.label)+'</b> — '+esc(s.detail)+'</li>'; }).join("\n      ");

    var html='<div style="max-width:680px;margin:0 auto;font-family:\'Malgun Gothic\',sans-serif;color:#141e2c;line-height:1.7;">\n'+
    '  <div style="background:#0b1f3a;color:#ffffff;padding:22px 20px;border-radius:10px;">\n'+
    '    <div style="font-size:12px;letter-spacing:2px;color:#a9c9e8;font-weight:bold;">WELLPERION · NOW HIRING</div>\n'+
    '    <div style="font-size:24px;font-weight:bold;margin-top:8px;">'+esc(d.titleLong)+'</div>\n'+
    '    <div style="font-size:14px;color:#c9daea;margin-top:6px;">'+esc(d.heroSub)+'</div>\n  </div>\n\n'+
    '  <p style="font-size:14px;color:#5c6b7e;margin:16px 4px;">'+esc(d.company.about)+'</p>\n\n'+
    '  <div style="text-align:center;margin:16px 0;">\n'+
    '    <img src="'+esc(d.urls.valuesDiagram)+'" alt="웰페리온 인재상 도표" style="max-width:320px;width:100%;height:auto;border:1px solid #dbe5ef;border-radius:8px;">\n  </div>\n\n'+
    '  <h3 style="color:#0b1f3a;border-left:4px solid #3f6fa0;padding-left:10px;margin:18px 4px 8px;">모집 개요</h3>\n'+
    '  <ul style="margin:0 4px;padding-left:20px;font-size:14px;">\n'+
    '      <li style="margin:4px 0;"><b>포지션</b> — '+esc(titleRank(d))+' · '+esc(d.dept)+'</li>\n'+
    '      <li style="margin:4px 0;"><b>고용형태</b> — '+esc(d.employmentType)+'</li>\n'+
    '      <li style="margin:4px 0;"><b>근무지</b> — '+esc(d.location)+'</li>\n'+
    '      <li style="margin:4px 0;"><b>급여</b> — '+esc(d.salary.monthly)+' ('+esc(d.salary.note)+')</li>\n  </ul>\n\n'+
    '  <h3 style="color:#0b1f3a;border-left:4px solid #3f6fa0;padding-left:10px;margin:18px 4px 8px;">담당 업무</h3>\n'+
    '  <ul style="margin:0 4px;padding-left:20px;font-size:14px;">\n      '+duties+'\n  </ul>\n\n'+
    '  <h3 style="color:#0b1f3a;border-left:4px solid #3f6fa0;padding-left:10px;margin:18px 4px 8px;">자격 요건</h3>\n'+
    '  <ul style="margin:0 4px;padding-left:20px;font-size:14px;">\n      '+req+'\n  </ul>\n\n'+
    '  <h3 style="color:#0b1f3a;border-left:4px solid #3f6fa0;padding-left:10px;margin:18px 4px 8px;">우대 사항</h3>\n'+
    '  <ul style="margin:0 4px;padding-left:20px;font-size:14px;">\n      '+pref+'\n  </ul>\n\n'+
    '  <h3 style="color:#0b1f3a;border-left:4px solid #3f6fa0;padding-left:10px;margin:18px 4px 8px;">근무 시간 · 휴무</h3>\n'+
    '  <ul style="margin:0 4px;padding-left:20px;font-size:14px;">\n      '+shift+'\n      <li style="margin:4px 0;"><b>휴무</b> — '+esc(d.off)+'</li>\n  </ul>\n\n'+
    '  <h3 style="color:#0b1f3a;border-left:4px solid #3f6fa0;padding-left:10px;margin:18px 4px 8px;">복지 · 성장</h3>\n'+
    '  <ul style="margin:0 4px;padding-left:20px;font-size:14px;">\n      '+ben+'\n  </ul>\n\n'+
    '  <div style="background:#0b1f3a;color:#ffffff;padding:18px 20px;border-radius:10px;margin-top:18px;">\n'+
    '    <div style="font-size:12px;color:#a9c9e8;font-weight:bold;">지원 및 문의</div>\n'+
    '    <div style="font-size:16px;font-weight:bold;margin-top:8px;">이메일 '+esc(d.contact.email)+'</div>\n'+
    '    <div style="font-size:16px;font-weight:bold;margin-top:4px;">전화 '+esc(d.contact.phone)+' ('+esc(d.contact.manager)+')</div>\n'+
    '    <div style="font-size:13px;color:#c9daea;margin-top:8px;">'+esc(d.contact.howto)+'</div>\n'+
    '    <div style="font-size:13px;color:#c9daea;margin-top:6px;">공고 상세 : '+esc(d.urls.recruitPage)+'</div>\n  </div>\n\n'+
    '  <p style="text-align:center;font-size:16px;font-weight:bold;color:#0b1f3a;margin:18px 4px;">'+esc(d.company.slogan)+'</p>\n</div>';
    return stripNonBMP(html);
  }

  /* ============ C. 당근알바 — 간결 텍스트 ============ */
  function danggeunText(d){
    var duties=d.duties.slice(0,3).map(function(x){return "· "+x;}).join("\n");
    return titleRank(d)+" 모집 ("+d.employmentType+")\n\n"+
    "📍 "+d.locationDetail+"\n🏛 "+d.company.oneLiner+", 웰페리온\n\n"+
    "한남동 프리미엄 스포츠·스파 클럽에서 함께 일할 "+titleRank(d)+"님을 찾습니다.\n\n"+
    "· 급여 : "+d.salary.monthly+" (수습기간 감액 없음)\n"+
    "· 근무 : "+d.shift[0].detail+" / 교대 근무\n"+
    "· 휴무 : "+d.off+"\n"+
    "· 학력·경력 무관 (신입 지원 가능)\n\n"+
    "주요 업무\n"+duties+"\n\n"+
    "우대 : 유관업무 경험자, 즉시출근 가능자\n\n"+
    "지원·문의\n· 이메일 "+d.contact.email+"\n· 전화 "+d.contact.phone+" ("+d.contact.manager+")\n\n"+
    "공고 상세 ▶ "+d.urls.recruitPage+"\n\n"+
    "가까운 한남동에서 오래 함께할 분을 기다립니다.";
  }

  /* ============ D. 다음카페 — 텍스트 + 이미지 안내(스포드림/호호요가 실사용 형식) ============ */
  function daumCafeText(d){
    var cafeKey=(d.communityCafes&&d.communityCafes[0])||"sportsdream";
    var cafeName=CAFE_NAME[cafeKey]||"커뮤니티 카페";
    var board=CAFE_BOARD[cafeKey]||"구인 게시판";
    var bar="═══════════════════════════════════════════════";
    var thin="───────────────────────────────────────────────";
    var duties=d.duties.slice(0,4).map(function(x){return "· "+x;}).join("\n");
    return bar+"\n "+cafeName+" 게시 재료 — "+d.title+" 공고\n (다음 카페 / 게시판: "+board+")\n"+bar+"\n\n"+
    "■ 첨부 이미지 (본문 상단에 삽입)\n"+
    "리크루팅 페이지 상단 'JPG 다운로드' 버튼으로 카드 이미지를 받아 첨부하세요.\n"+d.urls.recruitPage+"\n\n"+
    "■ 제목 (특수문자 없이 — 카페 규칙 준수)\n"+
    "한남동 웰페리온 "+d.title+" "+d.employmentType+" 채용\n\n"+
    "■ 본문 (이미지 아래에 붙여넣을 텍스트 — 검색·접근성용)\n"+
    "한남동 프리미엄 멤버십 스포츠 클럽 웰페리온에서 "+titleRank(d)+"을(를) 모집합니다.\n\n"+
    "모집 부문 : "+titleRank(d)+" ("+d.dept+")\n"+
    "고용 형태 : "+d.employmentType+"\n"+
    "근무 시간 : "+d.shift.map(function(s){return s.label+" "+s.detail;}).join(" / ")+"\n"+
    "휴무 : "+d.off+"\n"+
    "급여 : "+d.salary.monthly+" ("+d.salary.note+")\n"+
    "근무지 : "+d.location+"\n\n"+
    "주요 업무\n"+duties+"\n\n"+
    "지원 방법\n이메일 : "+d.contact.email+"\n문의 전화 : "+d.contact.phone+" ("+d.contact.manager+")\n상세 공고 : "+d.urls.recruitPage+"\n\n"+
    thin+"\n※ 카페 규칙: 1회사 1게시물(도배 금지) / 제목 2줄 이내·특수문자 금지 준수함.\n"+
    "※ 내용은 리크루팅 "+d.title+" 공고 실데이터 기준 — 창작 없음.";
  }

  global.CHANNEL_HUB = {
    SOURCES:SOURCES, fullData:fullData, matchSource:matchSource, urlsFor:urlsFor,
    esc:esc, titleRank:titleRank,
    gen:{ jobkorea:jobkoreaHtml, albamon:albamonHtml, danggeun:danggeunText, daumcafe:daumCafeText }
  };
})(window);
