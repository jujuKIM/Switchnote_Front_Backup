import React, { useEffect, useRef, useState } from 'react';
import {useParams} from 'react-router-dom'
import refreshIcon from './images/refreshIcon.png';
import copyIcon from './images/copyIcon.png';
import loadingIcon from './images/loading.gif';
import MyButton from './MyButton.js';
import MyTextarea from './MyTextarea.js';
import { CallGPT } from '../api/gpt';
import TextInput from './TextInput.js';
import { CallKoBERT } from '../api/kobert';
// import {generatePPT} from '../api/generatePPT.py'

function TxtInput({ getProjectById }) {
  const [projectTitle, setProjectTitle] = useState('');
  const [projectContent, setProjectContent] = useState('');
  const [project, setProject] = useState(null);
  const { projectId } = useParams();
  
  // 사용자 입력값 저장 상태
  const [userInput, setUserInput] = useState("");

  useEffect(() => {
    if (projectId) {
      const projectData = getProjectById(projectId);
      if (projectData) {
        setProjectContent(projectData.content); // 프로젝트 내용 저장
        setUserInput(projectData.content); // 프로젝트 내용이 Input이니까 userInput에도 동일한 내용 저장
        setProject(projectData); // 프로젝트 데이터 저장
        setProjectTitle(projectData.title); // 프로젝트 제목 저장
      }
    }
  }, [projectId]);

  // 텍스트 새로고침
  const handleClearText = () => {
    setProjectContent('');
    setUserInput('');
  };

  // 텍스트 복사
  const handleCopyText = async () => {
    await navigator.clipboard.writeText(userInput);
    alert('텍스트가 클립보드에 복사되었습니다.');
  };

  // ppt 생성 기능
  const handleSubmit = async () => {
    await handleCreatePPT(userInput);
    // transformGPTOutput(handleCreatePPT(userInput));

  }

  const [data, setData] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  // ppt 생성 함수
  const handleCreatePPT = async(input) => {
    try{
      setIsLoading(true);
      const message = await CallGPT({
        prompt: `${input}`});
      console.log(message);

      console.log(transformGPTOutput(message));
      
      //kobertResult 변수에 kobert 수행 결과가 들어 있음
      const kobertResult = await CallKoBERT({text: `${input}`})
      console.log(kobertResult);

      // const url = await ConvertPPT(transformGPTOutput(message));
      // console.log(url);
    } catch(error) {
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  };

  //gpt 결과를 {page:,type:,title:,subtitle:,content:} 형식으로 변환하는 함수
  const transformGPTOutput = (gptOutput) => {
    // '---' 기호를 기준으로 페이지 분리
    const pages = gptOutput.split('---');
  
    const database = [];
  
    // 페이지 타입과 해당하는 알파벳 문자 매핑
    const pageTypeMapping = {
        '[표지]': 'a',
        '[목차]': 'b',
        '[본문]': 'c',
        '[마무리]': 'd'
    };
  
    for (const page of pages) {
        const lines = page.split('\n');
  
        let title = "", subtitle = "", contentList = [], pageNumber = 0, pageType = "";
  
        for (const line of lines) {
            if (Object.keys(pageTypeMapping).some(pageTypeKey => line.includes(pageTypeKey))) {
                const matchedPageTypeKey = Object.keys(pageTypeMapping).find(pageTypeKey => line.includes(pageTypeKey));
  
                if (matchedPageTypeKey) {
                    pageType = pageTypeMapping[matchedPageTypeKey];
                }
            } else if (line.includes("페이지 번호:")) {
                pageNumber = parseInt(line.split("페이지 번호:")[1].trim());
            } else if (line.includes("제목:")) {
                title += line.split("제목:")[1].trim();
            } else if (line.includes("소제목:")) {
                subtitle += line.split("소제목:")[1].trim();
            } else if (line.includes("내용:") || line.includes("마무리 문장:")) {
                contentList.push(line.trim());
            } else {
                if (line.trim().length > 0) {
                    contentList.push(line.trim());
                }
            }
        }
  
        const dataDict = {
            page: pageNumber, 
            type: pageType,
            title: title, 
            subtitle: subtitle, 
            content: contentList
        };
  
        database.push(dataDict);
    }
  
    return database;
  };

  // 입력한 텍스트를 txt 파일로 저장
  const handleDownload = (title, content) => {
    const element = document.createElement("a");
    const file = new Blob([content], { type: "text/plain" });
    element.href = URL.createObjectURL(file);
    element.download = title ? `${title}.txt` : "Untitled.txt";
    document.body.appendChild(element); 
    element.click();
  };
  
  return (
    <div>
      <h3 style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>TEXT 변환, 그리고 PPT 생성</h3>

      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
        <label htmlFor="fileName"></label>
          <MyTextarea
            placeholder={project ? project.title : '파일명을 입력하세요'} 
            type={"title"}
            value={projectTitle}
            onChange={(e) => setProjectTitle(e.target.value)}
          />

        <label htmlFor="description"></label>
          <MyTextarea 
            placeholder={'부가설명을 입력하세요'}
            type={"small"}
            isLoading={isLoading}
          />
      </div>
      
      <div style={{ width: "100%", textAlign:"right", marginTop:'50px'}}>
        <img
          src={refreshIcon}
          alt="새로고침"
          onClick={handleClearText}
          style={{ cursor: 'pointer'}}
        />
      </div>

      <div>
        <TextInput 
          isLoading={isLoading} 
          onSubmit={setUserInput} 
          value={userInput}
        />
      </div>

      <div style={{ width: "100%", textAlign:"right" }}>
        <img
          src={copyIcon}
          alt="텍스트 복사"
          onClick={handleCopyText}
          style={{ cursor: 'pointer'}}
        />
      </div>
      
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap:'10px', marginTop:'50px'}}>
        {isLoading ? (
          <img src={loadingIcon} alt="Loading..." />
        ) : (
          <MyButton 
            text={'PPT 생성'}
            onClick={() => handleSubmit(userInput)}
            type={"blue"}
          />
        )}

        <MyButton text={'.txt 파일로 다운로드'}
          onClick={() => handleDownload(projectTitle, userInput)}
          type={"gray"}
        />
      </div>
    </div>
  );
}

export default TxtInput;
