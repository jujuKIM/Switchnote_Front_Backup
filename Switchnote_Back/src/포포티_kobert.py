# -*- coding: utf-8 -*-
"""포포티_koBERT

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/16ebN7wkUvMKEcTZXbBWBSqRvqvzD_Zf8

# koBERT 사용

공식문서
https://github.com/SKTBrain/KoBERT/blob/master/scripts/NSMC/naver_review_classifications_pytorch_kobert.ipynb
"""

from google.colab import drive
drive.mount('/content/drive')

!pip install mxnet
!pip install gluonnlp pandas tqdm
!pip install sentencepiece
!pip install transformers
!pip install torch

!pip install 'git+https://github.com/SKTBrain/KoBERT.git#egg=kobert_tokenizer&subdirectory=kobert_hf'

import torch
from torch import nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import gluonnlp as nlp
import numpy as np
from tqdm.notebook import tqdm

from transformers import AdamW
from transformers.optimization import get_cosine_schedule_with_warmup
from transformers import BertModel
from kobert_tokenizer import KoBERTTokenizer

tokenizer = KoBERTTokenizer.from_pretrained('skt/kobert-base-v1')
bertmodel = BertModel.from_pretrained('skt/kobert-base-v1', return_dict=False)
vocab = nlp.vocab.BERTVocab.from_sentencepiece(tokenizer.vocab_file, padding_token='[PAD]')

# GPU 사용
device = torch.device("cuda:0")

import pandas as pd
import numpy as np

data = pd.read_csv('/content/drive/MyDrive/한이음포포티/주제별대화_train.csv')
data = data.sample(frac=0.1) # 데이터가 너무 많아서 조금만 떼서 사용하려고 함..
data.info()

data = data.dropna()
data['text'] = data['text'].astype(str)
data['label'] = data['label'].astype(int)

data.info()

"""train, test 데이터로 나누기 (8:2 비율로 나눔)"""

from sklearn.model_selection import train_test_split
trainset, testset = train_test_split(data, test_size = 0.2, shuffle = True, random_state = 32)

print(type(trainset))
print(trainset)

print(type(testset))
print(testset)

"""데이터셋 토큰화"""

tokenizer = KoBERTTokenizer.from_pretrained('skt/kobert-base-v1', use_fast=True)
tok = nlp.data.BERTSPTokenizer(tokenizer, vocab, lower = False)

class BERTDataset(Dataset):
    def __init__(self, dataset, sent_idx, label_idx, bert_tokenizer, max_len,
                 pad=True):
        self.sentences = []
        self.labels = []

        for i in dataset:
            encoded = bert_tokenizer.encode_plus(
                i[sent_idx],
                add_special_tokens=True,
                max_length=max_len,
                return_attention_mask=True,
                padding='max_length',
                truncation=True
            )

            self.sentences.append((encoded['input_ids'], encoded['attention_mask']))
            self.labels.append(np.int32(i[label_idx]))

    def __getitem__(self, i):
        return [torch.tensor(data) for data in self.sentences[i]] + [torch.tensor(self.labels[i])]

    def __len__(self):
        return (len(self.labels))

"""파라미터 세팅"""

max_len = 512
batch_size = 16
warmup_ratio = 0.1
num_epochs = 5
max_grad_norm = 1
log_interval = 200
learning_rate = 5e-5

"""tokenization, dataloader 만들기"""

import gluonnlp as nlp

from transformers import BertModel
from kobert_tokenizer import KoBERTTokenizer

tokenizer = KoBERTTokenizer.from_pretrained('skt/kobert-base-v1')
bertmodel = BertModel.from_pretrained('skt/kobert-base-v1', return_dict=False)

# tokenizer.vocab_file로부터 vocab 생성
vocab = nlp.vocab.BERTVocab.from_sentencepiece(tokenizer.vocab_file, padding_token='[PAD]')

data_train = BERTDataset(trainset.values.tolist(), 0, 1, tokenizer, max_len, True)
data_test = BERTDataset(testset.values.tolist(), 0, 1, tokenizer, max_len, True)

train_dataloader = torch.utils.data.DataLoader(data_train,
                                               batch_size=batch_size,
                                               num_workers=1)
test_dataloader = torch.utils.data.DataLoader(data_test,
                                              batch_size=batch_size,
                                              num_workers=1)

"""koBERT 모델"""

import torch.nn as nn
from torch.utils.checkpoint import checkpoint

class BERTClassifier(nn.Module):
    def __init__(self,
                 bert,
                 hidden_size = 768,
                 num_classes= 21, # label이 1부터 20까지 있어서, 0을 포함하면 21개나 마찬가지!
                 dr_rate=None):
        super(BERTClassifier, self).__init__()
        self.bert = bert
        self.dr_rate = dr_rate

        self.classifier = nn.Linear(hidden_size , num_classes)

        if dr_rate:
            self.dropout = nn.Dropout(p=dr_rate)

    def forward(self, token_ids, attention_mask):
        _, pooler_output = checkpoint(self.bert.forward, token_ids.long(), attention_mask.float(), use_reentrant=True) # use_reentrant 매개변수 추가

        if self.dr_rate:
            out = self.dropout(pooler_output)
        else:
            out = pooler_output

        return self.classifier(out)

# BERT 모델 가져옴
model = BERTClassifier(bertmodel, dr_rate=0.5).to(device)

no_decay = ['bias', 'LayerNorm.weight']
optimizer_grouped_parameters = [
    {'params': [p for n, p in model.named_parameters() if not any(nd in n for nd in no_decay)], 'weight_decay': 0.01},
    {'params': [p for n, p in model.named_parameters() if any(nd in n for nd in no_decay)], 'weight_decay': 0.0}
]

optimizer = AdamW(optimizer_grouped_parameters, lr=learning_rate)
# optimizer = torch.optim.SGD(model.parameters(), lr=learning_rate)
loss_fn = nn.CrossEntropyLoss()

t_total = len(train_dataloader) * num_epochs
warmup_step = int(t_total * warmup_ratio)

scheduler = get_cosine_schedule_with_warmup(optimizer, num_warmup_steps=warmup_step, num_training_steps=t_total)

"""학습하기"""

for batch_id, (token_ids, attention_mask, label) in enumerate(train_dataloader):
    print(type(token_ids), type(attention_mask), type(label))
    break

from torch.cuda.amp import autocast, GradScaler

scaler = GradScaler()

def calc_accuracy(out, label):
    _, predicted = torch.max(out.data, 1)
    total = label.size(0)
    correct = (predicted == label).sum().item()
    return correct / total

for e in range(num_epochs):
    train_acc = 0.0
    model.train()

    for batch_id, (token_ids, attention_mask, label) in enumerate(train_dataloader):
        token_ids = token_ids.long().to(device)
        attention_mask = attention_mask.long().to(device)
        label = label.long().to(device)

        optimizer.zero_grad()

        with autocast():
            out = model(token_ids, attention_mask)
            loss = loss_fn(out, label)

        scaler.scale(loss).backward()

        # gradient clipping
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)


        scaler.step(optimizer)

        scheduler.step()

        scaler.update()

        train_acc += calc_accuracy(out, label)

    print("epoch {} train acc {}".format(e+1, train_acc / (len(train_dataloader))))

    torch.save({
      'epoch': e,
      'model_state_dict': model.state_dict(),
      'optimizer_state_dict': optimizer.state_dict(),
      'loss': loss,
     }, '/content/drive/MyDrive/한이음포포티/checkpoint.pth')

"""----

테스트하기

참고
https://velog.io/@sseq007/Kobert-%EB%AA%A8%EB%8D%B8-%EC%82%AC%EC%9A%A91
"""

data = [
  {'page': 1, 'type': 'a', 'title': '프로젝트 기획안모아줌 (ZOOM)2022학년도 2학기 고급 웹프로그래밍 과목 텀프로젝트', 'subtitle': '', 'content': ['작성자: 강태인, 김주연, 박가연']},
  {'page': 2, 'type': 'b', 'title': '목차', 'subtitle': '', 'content': ['1) 기획 배경', '2) 목표', '3) 벤치마킹', '4) 기능', '5) 구현 내용 및 방법', '6) 구현 내용 및 방법', '7) 개발 일정']},
  {'page': 3, 'type': 'c', 'title': '기획 배경', 'subtitle': '', 'content': ['1) 에브리타임 및 교내 커뮤니티 애플리케이션 외의 플랫폼 미비', '2) 교내 그룹 매칭 및 정보가 모두 게시글로 작성되기 때문에 해당하는 위치를 정확하게 알기 어려움', '내용:', '- 에브리타임 및 교내 커뮤니티 애플리케이션 외의 플랫폼이 부족하여 학생들의 소모임을 찾기 어려운 상황', '- 교내 그룹 매칭 및 정보가 게시글로 작성되어 위치 파악이 어려워 원하는 소모임을 찾기 힘듦']},
  {'page': 4, 'type': 'c', 'title': '목표', 'subtitle': '', 'content': ['1) 교내에서 학생 간 목적에 맞는 소모임을 캠퍼스 지도에 표시하는 방식을 통해 위치 공개적으로 그룹 매칭을 주선', '2) 교내 인증을 통한 회원제로 운영하여 안전하고 신뢰성 있는 매칭을 보장', '3) 커뮤니티 기능을 지도의 마킹 기능으로 제공하여 위치별 정보를 한눈에 알아볼 수 있도록 시각화', '내용:', '- 학생들이 쉽게 소모임을 찾을 수 있도록 지도를 활용하여 위치별로 소모임을 표시', '- 회원제를 도입하여 신원확인과 더불어 안전한 그룹 매칭을 보장', '- 커뮤니티 기능을 지도에 제공하여 학생들이 위치별 정보를 편리하게 확인 가능']},
  {'page': 5, 'type': 'c', 'title': '벤치마킹', 'subtitle': '', 'content': ['1) 모아줌', '2) 당근마켓', '3) 에브리타임', '내용:', '- 모아줌: 위치 정보 제공 O, 커뮤니티 O, 그룹 매칭 O', '- 당근마켓: 위치 정보 제공 O, 커뮤니티 X, 그룹 매칭 X', '- 에브리타임: 위치 정보 제공 X, 커뮤니티 O, 그룹 매칭 X']},
  {'page': 6, 'type': 'c', 'title': '기능', 'subtitle': '', 'content': ['1) 캠퍼스 지도', '2) 그룹 매칭 기능', '내용:', '- 캠퍼스 지도: 교내 지도를 기본적으로 제공', '- 그룹 매칭 기능: 지도에 위치를 마킹하여 소모임을 매칭, 목적별로 마커 색상을 다르게 구분']},
  {'page': 7, 'type': 'c', 'title': '기능', 'subtitle': '', 'content': ['3) 위치별 정보 공유', '내용:', '- 위치별로 실시간 분실물, 시설 문제점 등의 정보를 제공', '- 카테고리에 따라 정보 지속 시간을 다르게 표시']},
  {'page': 8, 'type': 'c', 'title': '기능', 'subtitle': '', 'content': ['4) 최적 경로 기능', '내용:', '- 건물 간의 최적 경로와 예상 이동 시간을 제공']},
  {'page': 9, 'type': 'c', 'title': '기능', 'subtitle': '', 'content': ['5) 커뮤니티', '내용:', '- 마커 정보를 세부적으로 탐색', '- 댓글 및 쪽지 기능 제공']},
  {'page': 10, 'type': 'c', 'title': '구현 내용 및 방법', 'subtitle': '', 'content': ['1) 회원가입/로그인', '내용:', '- 회원가입 및 로그인 기능 구현', '- 아이디와 비밀번호를 통한 회원 가입, 아이디는 학번으로 작성, 비밀번호는 NodeJS 암호화 모듈을 통해 암호화']},
  {'page': 11, 'type': 'd', 'title': '', 'subtitle': '', 'content': ['마무리 문장: 강력한 소모임 매칭과 정보 공유를 통해 학생들의 커뮤니티 활동을 즐거움과 편리함을 더하고, 성공적인 학업과 함께 풍요로운 대학 생활을 만들어나가기를 바랍니다.']}
]

text = ""
for content in data:
  text += " ".join(content['content'])

print(text)

def predict(predict_sentence, model, tokenizer, max_len, device):
    checkpoint = torch.load('/content/drive/MyDrive/한이음포포티/checkpoint2.pth')
    model.load_state_dict(checkpoint['model_state_dict'])

    data = [predict_sentence, '0']
    dataset_predict = BERTDataset([data], 0 , 1 , tokenizer , max_len)
    dataloader_predict = torch.utils.data.DataLoader(dataset_predict , batch_size=1 , num_workers=5)

    model.eval()

    for batch_id, (token_ids, valid_length,label) in enumerate(dataloader_predict):
        token_ids = token_ids.long().to(device)
        valid_length= valid_length.long().to(device)

        out = model(token_ids , valid_length).detach().cpu().numpy()

        test_eval=[]

        if np.argmax(out) in [11]:
            test_eval.append("과학기술")
        elif np.argmax(out) in [6]:
            test_eval.append("교육")
        elif np.argmax(out) in [18]:
            test_eval.append("금융경제")
        elif np.argmax(out) in [5,9]:
            test_eval.append("비즈니스산업")
        elif np.argmax(out) in [10]:
            test_eval.append("스포츠")
        elif np.argmax(out) in [14]:
            test_eval.append("역사종교")
        elif np.argmax(out) in [16,19]:
            test_eval.append("예술")
        elif np.argmax(out) in [1,2,7,8]:
            test_eval.append("음식")
        elif np.argmax(out) == 4:
            test_eval.append('IT/컴퓨터')

    print(f">> 입력하신 내용은 {test_eval[0]} 카테고리로 분류됩니다.")

model.to(device)
predict(text, model=model, tokenizer=tokenizer, max_len=max_len, device=device)

"""----

과학/기술 11

교육 6

금융/경제 18

비즈니스/산업 5 9

스포츠 10

역사/종교 14

예술 16 19

음식 1 2 7 8

인문학 15 20

의료 17

자연/여행 3 12 13

IT/컴퓨터 4


      "식음료": 1,
      "주거와 생활": 2,
      "교통": 3,
      "회사/아르바이트": 4,
      "군대": 5,
      "교육": 6,
      "가족": 7,
      "연애/결혼": 8,
      "반려동물": 9,
      "스포츠/레저": 10,
      "게임": 11,
      "여행": 12,
      "계절/날씨": 13,
      "사회이슈": 14,
      "타 국가 이슈": 15,
      "미용": 16,
      "건강": 17,
      "상거래 전반": 18,
      "방송/연예": 19,
      "영화/만화": 20
"""

